"""
M6: Communication & Explanation Engine
=======================================
Implements bounded customer-facing communication generation and internal
transparent decision explanations.

Adheres strictly to the M4 decision authority, deterministic template fallbacks,
and programmatic guardrail verification.
"""

import copy
from typing import Any, Callable, Dict, Optional, Tuple

from ml.llm.contracts import (
    ACTIVE_RECOVERY_ACTIONS,
    INACTIVE_ACTIONS,
    ApprovedCustomerContext,
    CustomerCommunication,
    DecisionExplanation,
)
from ml.llm.guardrails import (
    run_communication_guardrails,
    validate_approved_context,
    validate_decision_output,
)

# ---------------------------------------------------------------------------
# Deterministic Fallback Templates
# ---------------------------------------------------------------------------

def _format_amount(amount: Optional[float], currency: str = "INR") -> str:
    """Format currency amount cleanly."""
    curr_symbol = "₹" if currency == "INR" else f"{currency} "
    if amount is None:
        return "your recent transaction"
    return f"{curr_symbol}{amount:,.2f}"


def _get_greeting(name: Optional[str], segment: Optional[str]) -> str:
    """Produce neutral or approved greeting."""
    if name:
        return f"Dear {name},"
    if segment == "b2b":
        return "Dear Business Partner,"
    return "Dear Customer,"


def _render_deterministic_template(
    decision: str,
    ctx: ApprovedCustomerContext,
) -> Tuple[Optional[str], str]:
    """
    Render a safe, bounded, deterministic template based on action, channel, and segment.
    Returns (subject, body).
    """
    channel = ctx.channel or "email"
    segment = ctx.customer_segment or "b2c_returning"
    name = ctx.customer_display_name
    greeting = _get_greeting(name, segment)
    amt_str = _format_amount(ctx.amount, ctx.currency)

    # -----------------------------------------------------------------------
    # Inactive Actions (Non-Sendable notices)
    # -----------------------------------------------------------------------
    if decision in INACTIVE_ACTIONS:
        subject = f"Transaction Status Notice [{ctx.transaction_id}]"
        if decision == "wait":
            body = (
                f"{greeting}\n\n"
                f"Your transaction ({ctx.transaction_id}) for {amt_str} is currently being processed. "
                "No immediate action is required on your end while we await status confirmation from the bank."
            )
        elif decision == "close":
            body = (
                f"{greeting}\n\n"
                f"Your transaction ({ctx.transaction_id}) for {amt_str} has concluded. "
                "No further automated recovery attempts are scheduled for this request."
            )
        elif decision == "escalate":
            body = (
                f"{greeting}\n\n"
                f"Your transaction ({ctx.transaction_id}) for {amt_str} has been routed to our specialized support "
                "team for personalized review. An account specialist will reach out if assistance is required."
            )
        else: # no_action_required
            body = (
                f"{greeting}\n\n"
                f"Regarding transaction ({ctx.transaction_id}) for {amt_str}: No action is currently required. "
                "Thank you for your business."
            )
        return subject, body

    # -----------------------------------------------------------------------
    # Active Action: RETRY
    # -----------------------------------------------------------------------
    if decision == "retry":
        if channel == "sms":
            subject = None
            body = (
                f"Your payment of {amt_str} for ref #{ctx.transaction_id} faced a temporary processing delay. "
                "We are automatically re-attempting the transaction. No action is required."
            )
        elif channel == "whatsapp":
            subject = None
            body = (
                f"{greeting}\n\n"
                f"Your payment of {amt_str} (Ref: {ctx.transaction_id}) experienced a temporary bank delay. "
                "Our system is automatically re-attempting the charge for you shortly. You do not need to take any action."
            )
        else: # email / default
            subject = f"Payment Processing Update for Transaction #{ctx.transaction_id}"
            if segment == "b2b":
                body = (
                    f"{greeting}\n\n"
                    f"We encountered a temporary network delay processing invoice payment {amt_str} (Ref: {ctx.transaction_id}). "
                    "Our payment infrastructure is automatically scheduling a retry. No manual intervention is needed at this time."
                )
            else:
                body = (
                    f"{greeting}\n\n"
                    f"We noticed a temporary issue processing your payment of {amt_str} for transaction #{ctx.transaction_id}. "
                    "We are automatically retrying the payment for you. There is no need to make a duplicate payment."
                )
        return subject, body

    # -----------------------------------------------------------------------
    # Active Action: PAYMENT_LINK
    # -----------------------------------------------------------------------
    if decision == "payment_link":
        link = ctx.approved_payment_link or ""
        if channel == "sms":
            subject = None
            body = (
                f"Complete your payment of {amt_str} for ref #{ctx.transaction_id} securely using this link: {link}"
            )
        elif channel == "whatsapp":
            subject = None
            body = (
                f"{greeting}\n\n"
                f"To complete your payment of {amt_str} (Ref: {ctx.transaction_id}), please use our secure payment link:\n"
                f"{link}\n\n"
                "Thank you for choosing our service."
            )
        else: # email / default
            subject = f"Secure Payment Link for Transaction #{ctx.transaction_id}"
            if segment == "b2b":
                body = (
                    f"{greeting}\n\n"
                    f"Please find below the secure checkout link to settle the pending balance of {amt_str} "
                    f"for transaction #{ctx.transaction_id}:\n\n"
                    f"{link}\n\n"
                    "Please let our team know if you need an updated remittance invoice."
                )
            else:
                body = (
                    f"{greeting}\n\n"
                    f"To finalize your order of {amt_str} for transaction #{ctx.transaction_id}, "
                    f"please complete your payment through the secure link below:\n\n"
                    f"{link}\n\n"
                    "If you have already paid, please disregard this message."
                )
        return subject, body

    # -----------------------------------------------------------------------
    # Active Action: REMINDER
    # -----------------------------------------------------------------------
    if decision == "reminder":
        if channel == "sms":
            subject = None
            body = (
                f"Friendly reminder: Your payment of {amt_str} for transaction #{ctx.transaction_id} remains pending. "
                "Please check your payment method to complete the transaction."
            )
        elif channel == "whatsapp":
            subject = None
            body = (
                f"{greeting}\n\n"
                f"This is a gentle reminder that payment of {amt_str} for transaction #{ctx.transaction_id} is pending. "
                "Please verify your payment details when convenient."
            )
        else: # email / default
            subject = f"Reminder: Pending Payment for Transaction #{ctx.transaction_id}"
            if segment == "b2b":
                body = (
                    f"{greeting}\n\n"
                    f"This is a courteous reminder regarding the outstanding balance of {amt_str} for transaction #{ctx.transaction_id}. "
                    "Kindly ensure your authorization details are active to prevent service interruption."
                )
            else:
                body = (
                    f"{greeting}\n\n"
                    f"Just a friendly reminder that your payment of {amt_str} for transaction #{ctx.transaction_id} is pending. "
                    "Please check your card or account to ensure everything is in order."
                )
        return subject, body

    # -----------------------------------------------------------------------
    # Active Action: DISCOUNT
    # -----------------------------------------------------------------------
    if decision == "discount":
        disc_p = ctx.approved_discount_percent or 0.0
        disc_amt = (ctx.amount * (disc_p / 100.0)) if ctx.amount is not None else 0.0
        final_amt = (ctx.amount - disc_amt) if ctx.amount is not None else 0.0
        final_amt_str = _format_amount(final_amt, ctx.currency)

        if channel == "sms":
            subject = None
            body = (
                f"Exclusive offer: We have applied a {disc_p:.0f}% discount to transaction #{ctx.transaction_id}. "
                f"Your adjusted payable amount is {final_amt_str}."
            )
        elif channel == "whatsapp":
            subject = None
            body = (
                f"{greeting}\n\n"
                f"Special concession: A {disc_p:.0f}% discount has been applied to transaction #{ctx.transaction_id} (originally {amt_str}). "
                f"Your new payable balance is {final_amt_str}."
            )
        else: # email / default
            subject = f"Special Concession: {disc_p:.0f}% Discount on Transaction #{ctx.transaction_id}"
            if segment == "b2b":
                body = (
                    f"{greeting}\n\n"
                    f"As a valued business customer, we have authorized a {disc_p:.0f}% discount on transaction #{ctx.transaction_id} "
                    f"(original invoice: {amt_str}). Your adjusted payable amount is {final_amt_str}.\n\n"
                    "We appreciate your continued partnership."
                )
            else:
                body = (
                    f"{greeting}\n\n"
                    f"Good news! We have approved a special {disc_p:.0f}% discount on your transaction #{ctx.transaction_id} "
                    f"(originally {amt_str}). You now only need to pay {final_amt_str} to complete your order."
                )
        return subject, body

    # Fallback default
    return "Payment Notification", f"{greeting}\n\nRegarding transaction #{ctx.transaction_id} of {amt_str}."


# ---------------------------------------------------------------------------
# Public Interface: compose_customer_communication
# ---------------------------------------------------------------------------

def compose_customer_communication(
    decision_output: Dict[str, Any],
    approved_context: Optional[Any] = None,
    generator: Optional[Callable[[Dict[str, Any], ApprovedCustomerContext], Any]] = None,
) -> Dict[str, Any]:
    """
    Compose customer-facing communication for an M4 decision.
    Validates decision output, checks approved context, runs guardrails,
    and guarantees zero data leakage with safe deterministic fallbacks.

    Parameters
    ----------
    decision_output : dict
        Authoritative decision output from M4 make_decision().
    approved_context : dict or ApprovedCustomerContext, optional
        Customer context supplied from external verified stores.
    generator : callable, optional
        Optional custom generative function (f(decision_output, context) -> str | dict).
        Subjected to strict post-generation programmatic guardrails.

    Returns
    -------
    dict
        Dictionary representation of CustomerCommunication.
    """
    # 1. Defensive copies
    dec_copy = copy.deepcopy(decision_output)
    
    # 2. Validate decision output
    val_dec = validate_decision_output(dec_copy)
    if not val_dec["is_valid"]:
        # Decision output itself is malformed: fail closed
        return CustomerCommunication(
            transaction_id=str(dec_copy.get("transaction_id", "unknown") if isinstance(dec_copy, dict) else "unknown"),
            decision="unknown",
            sendable=False,
            channel="none",
            subject=None,
            body="Invalid decision input provided. Communication suppressed.",
            customer_display_name=None,
            generation_mode="non_sendable_fallback",
            guardrail_status={
                "passed": False,
                "checks": [],
                "violations": val_dec["errors"],
            },
            fallback_used=True,
            metadata={"validation_errors": val_dec["errors"]},
        ).to_dict()

    decision = dec_copy["decision"]
    txn_id = dec_copy["transaction_id"]

    # 3. Validate approved context
    val_ctx = validate_approved_context(approved_context, decision)
    if not val_ctx["is_valid"]:
        # Context invalid for this action: fail closed to non-sendable fallback
        return CustomerCommunication(
            transaction_id=txn_id,
            decision=decision,
            sendable=False,
            channel=getattr(approved_context, "channel", "none") if approved_context else "none",
            subject=None,
            body="Approved customer context validation failed. Communication suppressed.",
            customer_display_name=getattr(approved_context, "customer_display_name", None) if approved_context else None,
            generation_mode="non_sendable_fallback",
            guardrail_status={
                "passed": False,
                "checks": [],
                "violations": val_ctx["errors"],
            },
            fallback_used=True,
            metadata={"context_errors": val_ctx["errors"]},
        ).to_dict()

    ctx: ApprovedCustomerContext = val_ctx["context"]
    channel = ctx.channel or "email"

    # 4. Handle Inactive / Terminal Actions
    if decision in INACTIVE_ACTIONS:
        subject, body = _render_deterministic_template(decision, ctx)
        g_status = run_communication_guardrails(body, decision, ctx, dec_copy)
        return CustomerCommunication(
            transaction_id=txn_id,
            decision=decision,
            sendable=False, # Inactive actions are NEVER sendable recovery offers
            channel=channel,
            subject=subject,
            body=body,
            customer_display_name=ctx.customer_display_name,
            generation_mode="non_sendable_fallback",
            guardrail_status=g_status.to_dict(),
            fallback_used=True,
            metadata={"reason": f"Action '{decision}' is not an active recovery outreach."},
        ).to_dict()

    # 5. Active Actions: check for required context completeness to be sendable
    missing_context_errors = []
    if ctx.amount is None:
        missing_context_errors.append("Missing transaction amount in approved context.")
    if decision == "payment_link" and not ctx.approved_payment_link:
        missing_context_errors.append("Missing approved_payment_link for payment_link action.")
    if decision == "discount" and ctx.approved_discount_percent is None:
        missing_context_errors.append("Missing approved_discount_percent for discount action.")

    if missing_context_errors:
        # Cannot be sendable without necessary financial facts
        subject, body = _render_deterministic_template(decision, ctx)
        return CustomerCommunication(
            transaction_id=txn_id,
            decision=decision,
            sendable=False,
            channel=channel,
            subject=subject,
            body=body,
            customer_display_name=ctx.customer_display_name,
            generation_mode="non_sendable_fallback",
            guardrail_status={
                "passed": False,
                "checks": [],
                "violations": missing_context_errors,
            },
            fallback_used=True,
            metadata={"missing_context": missing_context_errors},
        ).to_dict()

    # 6. Generator execution (if supplied)
    if generator is not None and callable(generator):
        try:
            gen_output = generator(dec_copy, ctx)
            if isinstance(gen_output, dict):
                candidate_body = gen_output.get("body", "")
                candidate_subject = gen_output.get("subject", None)
            elif isinstance(gen_output, str):
                candidate_body = gen_output
                candidate_subject = None
            else:
                candidate_body = ""
                candidate_subject = None

            # Execute programmatic guardrails on generator output
            g_status = run_communication_guardrails(candidate_body, decision, ctx, dec_copy)

            if g_status.passed:
                # Generator succeeded and verified safe
                return CustomerCommunication(
                    transaction_id=txn_id,
                    decision=decision,
                    sendable=True,
                    channel=channel,
                    subject=candidate_subject,
                    body=candidate_body,
                    customer_display_name=ctx.customer_display_name,
                    generation_mode="generator_verified",
                    guardrail_status=g_status.to_dict(),
                    fallback_used=False,
                    metadata={"generator_used": True},
                ).to_dict()
            else:
                # Generator failed guardrails: discard and fall back to deterministic template
                fb_subject, fb_body = _render_deterministic_template(decision, ctx)
                fb_status = run_communication_guardrails(fb_body, decision, ctx, dec_copy)
                return CustomerCommunication(
                    transaction_id=txn_id,
                    decision=decision,
                    sendable=fb_status.passed,
                    channel=channel,
                    subject=fb_subject,
                    body=fb_body,
                    customer_display_name=ctx.customer_display_name,
                    generation_mode="fallback_due_to_guardrail",
                    guardrail_status=fb_status.to_dict(),
                    fallback_used=True,
                    metadata={
                        "generator_violations": g_status.violations,
                        "rejected_generator_body": candidate_body,
                    },
                ).to_dict()

        except Exception as e:
            # Generator threw runtime error: fall back safely
            fb_subject, fb_body = _render_deterministic_template(decision, ctx)
            fb_status = run_communication_guardrails(fb_body, decision, ctx, dec_copy)
            return CustomerCommunication(
                transaction_id=txn_id,
                decision=decision,
                sendable=fb_status.passed,
                channel=channel,
                subject=fb_subject,
                body=fb_body,
                customer_display_name=ctx.customer_display_name,
                generation_mode="fallback_due_to_guardrail",
                guardrail_status=fb_status.to_dict(),
                fallback_used=True,
                metadata={"generator_exception": str(e)},
            ).to_dict()

    # 7. Pure Deterministic Template Generation
    tmpl_subject, tmpl_body = _render_deterministic_template(decision, ctx)
    tmpl_status = run_communication_guardrails(tmpl_body, decision, ctx, dec_copy)

    return CustomerCommunication(
        transaction_id=txn_id,
        decision=decision,
        sendable=tmpl_status.passed,
        channel=channel,
        subject=tmpl_subject,
        body=tmpl_body,
        customer_display_name=ctx.customer_display_name,
        generation_mode="deterministic_template",
        guardrail_status=tmpl_status.to_dict(),
        fallback_used=False,
        metadata={"generator_used": False},
    ).to_dict()


# ---------------------------------------------------------------------------
# Public Interface: explain_decision
# ---------------------------------------------------------------------------

def explain_decision(decision_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate an internal transparent explanation of an M4 decision for operators,
    merchants, and auditors.

    Explains policy safety blocks, economic value rankings, and decision types.
    Does not mutate input dictionary.

    Parameters
    ----------
    decision_output : dict
        Decision dictionary produced by M4 make_decision().

    Returns
    -------
    dict
        Dictionary representation of DecisionExplanation.
    """
    # 1. Defensive copy & validation
    dec_copy = copy.deepcopy(decision_output)
    val = validate_decision_output(dec_copy)

    if not val["is_valid"]:
        return DecisionExplanation(
            transaction_id=str(dec_copy.get("transaction_id", "unknown") if isinstance(dec_copy, dict) else "unknown"),
            decision="invalid",
            decision_type="validation_error",
            decision_reason=f"Malformed decision dictionary: {val['errors']}",
            escalation_required=False,
            terminal=False,
            selected_probability=None,
            selected_ev=None,
            summary_explanation="Decision output failed schema validation.",
            policy_rationale="No policy rationale available due to invalid decision structure.",
            economic_rationale="No economic rationale available.",
            allowed_actions=[],
            blocked_actions={},
            model_version="unknown",
            policy_version="unknown",
            decision_engine_version="unknown",
        ).to_dict()

    txn_id = dec_copy["transaction_id"]
    decision = dec_copy["decision"]
    decision_type = dec_copy["decision_type"]
    decision_reason = dec_copy["decision_reason"]
    escalation = dec_copy["escalation_required"]
    terminal = dec_copy["terminal"]
    prob = dec_copy.get("selected_probability")
    ev = dec_copy.get("selected_ev")
    allowed = dec_copy.get("allowed_actions", [])
    blocked = dec_copy.get("blocked_actions", {})
    model_ver = dec_copy.get("model_version", "N/A")
    policy_ver = dec_copy.get("policy_version", "N/A")
    engine_ver = dec_copy.get("decision_engine_version", "N/A")
    action_analysis = dec_copy.get("action_analysis", {})

    # 2. Build Policy Rationale
    policy_lines = []
    if blocked:
        policy_lines.append(f"M3 Policy Engine restricted {len(blocked)} action(s):")
        for act, reasons in sorted(blocked.items()):
            if isinstance(reasons, list):
                r_str = ", ".join(reasons)
            else:
                r_str = str(reasons)
            policy_lines.append(f"  • '{act}': blocked by [{r_str}]")
    else:
        policy_lines.append("All standard actions were permitted by M3 safety rules.")

    if escalation:
        policy_lines.append("High-risk or high-value thresholds triggered mandatory human escalation.")
    if terminal:
        policy_lines.append("Transaction reached a terminal non-recovery state.")

    policy_rationale = "\n".join(policy_lines)

    # 3. Build Economic Rationale
    econ_lines = []
    if decision_type == "ev_optimization":
        ev_str = f"₹{ev:,.2f}" if ev is not None else "N/A"
        prob_str = f"{prob:.4f}" if prob is not None else "N/A"
        econ_lines.append(
            f"Action '{decision}' maximized Expected Net Value ({ev_str}) with predicted P(recovery)={prob_str}."
        )
        if len(action_analysis) > 1:
            econ_lines.append("Comparative EV across permitted candidate set:")
            for act, data in sorted(action_analysis.items(), key=lambda x: -x[1].get("expected_net_value", 0.0)):
                a_ev = data.get("expected_net_value", 0.0)
                a_prob = data.get("predicted_probability", 0.0)
                a_cost = data.get("intervention_cost", 0.0)
                econ_lines.append(
                    f"  • {act:15s} EV: ₹{a_ev:,.2f} (P={a_prob:.4f}, Cost=₹{a_cost:.1f})"
                )
    elif decision_type == "single_permitted_action":
        econ_lines.append(f"Only one action ('{decision}') was permitted by M3 policy.")
    elif decision_type == "terminal_forced_action":
        econ_lines.append(
            f"Terminal state enforced single final action '{decision}' (reason: {decision_reason})."
        )
    elif decision_type == "escalation_only":
        econ_lines.append("Escalation required; automated economic scoring bypassed for human routing.")
    else:
        econ_lines.append(f"Decision resolved via {decision_type} ({decision_reason}).")

    economic_rationale = "\n".join(econ_lines)

    # 4. Build Summary
    if escalation:
        summary = f"Transaction {txn_id} routed to manual escalation by M3 policy rules ({decision_reason})."
    elif terminal:
        summary = f"Transaction {txn_id} marked terminal; forced action '{decision}' applied."
    elif decision_type == "ev_optimization":
        ev_fmt = f"₹{ev:,.2f}" if ev is not None else "N/A"
        summary = (
            f"Selected action '{decision}' for transaction {txn_id} via EV optimization "
            f"yielding highest expected net recovery of {ev_fmt}."
        )
    else:
        summary = f"Selected action '{decision}' for transaction {txn_id} via {decision_type}."

    return DecisionExplanation(
        transaction_id=txn_id,
        decision=decision,
        decision_type=decision_type,
        decision_reason=decision_reason,
        escalation_required=escalation,
        terminal=terminal,
        selected_probability=prob,
        selected_ev=ev,
        summary_explanation=summary,
        policy_rationale=policy_rationale,
        economic_rationale=economic_rationale,
        allowed_actions=allowed,
        blocked_actions=blocked,
        model_version=model_ver,
        policy_version=policy_ver,
        decision_engine_version=engine_ver,
    ).to_dict()
