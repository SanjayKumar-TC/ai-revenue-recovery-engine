# AI Revenue Recovery Decision Engine

> A transparent, policy-constrained AI decision engine for intelligent revenue and payment recovery.

The **AI Revenue Recovery Decision Engine** determines the safest and economically best permitted action for every revenue-at-risk event.

The system combines **machine learning, expected-value optimization, deterministic policy enforcement, communication safety, persistent auditability, a real FastAPI backend, an AI Studio dashboard, and Gmail-based operational reporting** into a complete end-to-end decision workflow.

---

## Overview

Payment failures and revenue-at-risk events can have very different causes and require different recovery strategies.

Instead of applying a single recovery action to every failed transaction, this system:

1. Accepts customer and transaction context.
2. Determines which recovery actions are eligible.
3. Estimates action-conditional recovery probability.
4. Calculates expected economic value.
5. Applies deterministic policy and safety constraints.
6. Selects the best permitted action.
7. Generates communication and fallback information.
8. Stores the decision in a persistent audit trail.
9. Displays the decision through an AI Studio dashboard.
10. Sends an operational decision report through Gmail.

### Core Principle

> **Select the safest economically best action that is permitted by policy.**

---

## System Architecture

```text
                         ┌──────────────────────────┐
                         │ Customer / Transaction   │
                         │         Context          │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Action Eligibility       │
                         │   failure_type based    │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ ML Recovery Model        │
                         │ Logistic Regression      │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Expected Net Value       │
                         │ + Decision Engine        │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Deterministic Policy     │
                         │       Constraints        │
                         └────────────┬─────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │ Final Permitted Action   │
                         └────────────┬─────────────┘
                                      │
                       ┌──────────────┴──────────────┐
                       ▼                             ▼
              ┌──────────────────┐         ┌──────────────────┐
              │ Communication    │         │ Persistent Audit │
              │ + Fallback       │         │      Trail       │
              └────────┬─────────┘         └────────┬─────────┘
                       │                             │
                       ▼                             ▼
              ┌──────────────────┐         ┌──────────────────┐
              │ AI Studio        │         │ Audit Retrieval  │
              │ Dashboard        │         │    /audit/...    │
              └────────┬─────────┘         └──────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Gmail Decision   │
              │ Report Delivery  │
              └──────────────────┘
```

---

## Key Features

- **Action-conditional machine learning**
- **Expected Net Value optimization**
- **Deterministic policy constraints**
- **Recovery probability estimation**
- **Communication and fallback handling**
- **Persistent and queryable audit trail**
- **Trace-based decision/audit correlation**
- **Real FastAPI backend**
- **AI Studio dashboard integration**
- **Real Gmail decision-report delivery**
- **Stress testing and fault injection**
- **Reproducible verification workflow**

---

# Decision Engine

The system does not simply select the action with the highest recovery probability.

Instead, it evaluates the economic value of eligible actions while respecting policy constraints.

Conceptually:

```text
Final Action
    =
argmax(Expected Net Value)
    subject to
action eligibility + policy constraints
```

This separation ensures that the machine-learning model does not have unrestricted authority over the final recovery decision.

---

# Supported Recovery Actions

The decision engine supports eight recovery actions:

```text
retry
payment_link
reminder
discount
wait
close
escalate
no_action_required
```

Unknown backend actions are not silently remapped.

---

# Failure Types

The system supports the following revenue-at-risk failure types:

| Failure Type |
|---|
| `temporary_bank_decline` |
| `network_timeout` |
| `customer_abandoned` |
| `card_expired` |
| `risk_block` |
| `subscription_mandate_fail` |
| `insufficient_funds` |

---

# Milestone Roadmap

| Milestone | Description | Status |
|:---:|---|:---:|
| M1 | Synthetic Data Generator | ✅ Complete |
| M2 | Action-Conditional Logistic Regression | ✅ Complete |
| M3 | Deterministic Policy Engine | ✅ Complete |
| M4 | Expected Net Value + Decision Engine | ✅ Complete |
| M5 | Fixed Baseline + Experiment | ✅ Complete |
| M6 | Bounded Communication Layer | ✅ Complete |
| M7 | Audit Trail | ✅ Complete |
| M8 | FastAPI Backend | ✅ Complete |
| M9 | Dashboard Integration | ✅ Complete |
| M10 | Stress Testing + Hardening | ✅ Complete |
| M11 | Demo, Evidence + Documentation | ✅ Complete |

---

# M1 — Synthetic Data Generator

## Dataset

The synthetic data generator produces:

- **3,500** synthetic customers
- **10,000** failed transactions
- Customer and transaction context
- Failure types
- Eligible recovery actions
- Action-specific recovery outcomes

The generator uses:

```text
Seed = 42
```

to support deterministic and reproducible generation.

## Data Generation Pipeline

```text
Revenue-at-risk event
        ↓
Customer + transaction context
        ↓
Action eligibility
        ↓
Latent score
        ↓
Sigmoid probability
        ↓
Sampled recovery outcome
        ↓
Action-expanded dataset
```

## Action Eligibility

Action eligibility is keyed on:

```text
failure_type
```

rather than `event_type`.

`event_type` is a derived labeling/reporting field and does not determine which actions are scored.

## Hidden Truth

The data generator uses a latent-score → sigmoid → sampled-outcome mechanism.

The following information is excluded from model features:

- `latent_score`
- `true_prob_HIDDEN`
- Outcome-generation noise
- Future outcomes
- Future transaction information

The hidden-truth dataset is reserved for evaluation/debugging.

## Leakage Prevention

Customer-level train/validation/test splitting is used to reduce entity leakage.

Explicit interaction features include:

- `failure_type × action`
- `segment × action`

---

# M2 — Action-Conditional Machine Learning

The recovery model estimates the probability of recovery for a specific **transaction-action combination**.

The model operates on model-safe features and does not receive hidden outcome-generation information.

This enables the decision engine to compare the expected recovery behavior of multiple eligible actions for the same transaction.

---

# M3 — Deterministic Policy Engine

The policy layer constrains the machine-learning output before the final action is selected.

Relevant decision factors include:

- Failure type
- Customer context
- Attempt number
- Contact fatigue
- Recovery state
- Time since failure
- Risk conditions
- Action eligibility

The architecture separates:

```text
Machine Learning
       ↓
Economic Evaluation
       ↓
Policy Constraints
       ↓
Final Decision
```

This provides a controlled decision boundary between probabilistic prediction and business/safety rules.

---

# M4 — Expected Net Value + Decision Engine

The decision engine evaluates permitted actions using expected economic value.

The selected action is based on the **highest permitted Expected Net Value**, rather than probability alone.

The decision response contains:

- Transaction ID
- Trace ID
- Selected action
- Decision type
- Decision reason
- Escalation requirement
- Terminal state
- Selected expected value
- Selected probability
- Policy version
- Communication information

---

# M5 — Baseline & Experiment

M5 evaluates recovery decision behavior under controlled baseline and experimental conditions.

The project maintains separation between:

- Training data
- Evaluation data
- Hidden truth
- Decision outputs

This supports controlled evaluation without exposing hidden outcome-generation information to the decision model.

---

# M6 — Communication & Fallback Layer

The communication layer determines whether a recovery message is sendable and which channel should be used.

### Supported Channels

- Email
- SMS
- WhatsApp
- None

Communication state includes:

```text
Sendable
Channel
Message Body
Fallback Used
```

The system explicitly separates **message generation** from **message delivery**.

A generated customer message does not imply that the message was delivered.

---

# M7 — Persistent Audit Trail

The system maintains a persistent and queryable audit trail.

Audit records include:

- `trace_id`
- `timestamp`
- `transaction_id`
- `selected_action`
- `decision_type`
- `decision_reason`
- `policy_version`
- `model_version`
- `decision_engine_version`
- `rules_fired`
- `escalation_required`
- `terminal`
- `selected_ev`
- `selected_probability`
- Communication sendability
- Communication channel
- Fallback status

The `trace_id` provides the primary link between a decision response and its stored audit record.

> **Auditability:** The audit trail is persistent and queryable. It is not claimed to provide cryptographic immutability.

---

# M8 — FastAPI Backend

The decision engine is exposed through a real FastAPI backend.

## API Endpoints

### Health Check

```http
GET /health
```

### Decision Execution

```http
POST /decide
```

### Audit Retrieval

```http
GET /audit/{transaction_id}
```

### Gmail Report Delivery

```http
POST /report/email
```

The backend is the authoritative execution layer for real decision results.

---

# M9 — AI Studio Dashboard

The AI Studio dashboard provides the visual interface for interacting with the real backend.

The dashboard does not independently calculate mock decisions.

## Decision Flow

```text
AI Studio Dashboard
        ↓
POST /decide
        ↓
FastAPI Backend
        ↓
Decision Engine
        ↓
Real Decision Response
        ↓
AI Studio Dashboard
```

## Audit Flow

```text
AI Studio Dashboard
        ↓
GET /audit/{transaction_id}
        ↓
FastAPI Backend
        ↓
Persistent Audit Store
        ↓
Audit Record
```

### Dashboard Information

The dashboard displays:

- Recommended Action
- Decision Type
- Decision Reason
- Recovery Probability
- Expected Value
- Escalation
- Terminal State
- Communication State
- Trace ID
- Policy Version
- Audit Information

---

# M10 — Stress Testing & Hardening

The system includes stress and fault-injection testing covering areas such as:

- Decision execution
- Boundary behavior
- Contention
- Fault conditions
- Missing context conditions
- Model-related failures
- Audit behavior
- Load behavior

The objective is to verify controlled system behavior under adverse and unusual conditions.

---

# M11 — Final Evidence & Documentation

M11 consolidates:

- Final demonstration
- Evidence collection
- Reproducibility procedures
- Verification workflows
- Project documentation

## Verification Areas

The final verification covered:

- Backend health
- Real decision execution
- Audit retrieval
- Trace convergence
- Communication safety
- Action coverage
- Persistent auditability
- Dashboard integration
- Reproducibility procedures

## Action Coverage

All eight supported actions are implemented:

```text
retry
payment_link
reminder
discount
wait
close
escalate
no_action_required
```

Not every supported action is naturally selected under every live scenario.

Some actions, including `reminder` and `escalate`, are supported by the decision engine but were not naturally selected in the observed live verification scenarios.

This distinction is explicitly documented rather than hidden.

---

# Gmail Decision Report

The system provides real operational decision-report delivery through Gmail.

The dashboard includes an:

```text
Email Report
```

action.

## Delivery Architecture

```text
AI Studio Dashboard
        ↓
sendEmailReport()
        ↓
POST /report/email
        ↓
FastAPI
        ↓
Gmail SMTP
        ↓
Actual Gmail Inbox
```

## SMTP Configuration

```text
Host: smtp.gmail.com
Port: 587
Security: STARTTLS
Authentication: Gmail App Password
```

SMTP credentials are loaded through environment variables and are not hard-coded into the source code.

## Report Contents

The report contains:

- Transaction ID
- Amount
- Failure Type
- Recommended Action
- Decision Type
- Recovery Probability
- Expected Value
- Escalation
- Terminal
- Trace ID
- Policy Version
- Communication Status
- Fallback Status

It also includes the **actual communication message body returned by the backend**.

The customer message is explicitly identified as being included for reporting/audit purposes only.

It does **not** claim that the customer message was delivered to the customer.

## End-to-End Verification

The Gmail feature was verified through the complete flow:

```text
Real Decision
     ↓
AI Studio Dashboard
     ↓
Email Report
     ↓
POST /report/email
     ↓
Gmail SMTP
     ↓
Actual Gmail Inbox
```

The decision report was successfully received in the configured Gmail inbox.

**Gmail Decision Report Delivery: VERIFIED ✅**

---

# Security

Sensitive configuration must remain outside source control.

The local `.env` file contains SMTP credentials and must **never** be committed.

Example configuration:

```env
REPORT_EMAIL_HOST=smtp.gmail.com
REPORT_EMAIL_PORT=587
REPORT_EMAIL_USERNAME=your-email@gmail.com
REPORT_EMAIL_PASSWORD=your-app-password
REPORT_EMAIL_FROM=your-email@gmail.com
```

### Never expose or commit

- Gmail App Passwords
- SMTP credentials
- Private API credentials
- Other sensitive configuration

Runtime-generated files, databases, caches, and temporary artifacts should remain outside source-code commits where appropriate.

---

# Reproducibility

The project emphasizes reproducibility through:

- Deterministic synthetic-data generation
- Fixed random seed
- Customer-level dataset splitting
- Explicit feature construction
- Real backend API execution
- Trace-based decision/audit correlation
- Recorded evidence snapshots
- Documented verification procedures

---

# Repository Structure

```text
recovery/
│
├── api/
│   ├── main.py
│   ├── schemas.py
│   └── email_report.py
│
├── ml/
│   ├── audit/
│   ├── decision/
│   ├── evaluation/
│   ├── experiment/
│   ├── llm/
│   └── policy/
│
├── frontend/
│
├── revenue-recovery-engine-ai-studio/
│   ├── src/
│   │   ├── api/
│   │   └── components/
│   └── vite.config.ts
│
├── test_m10/
│
├── requirements.txt
├── README.md
└── .gitignore
```

---

# Installation

## Backend

From the project root:

```bash
cd C:\Users\ADMIN\Desktop\recovery
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the backend:

```bash
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Backend:

```text
http://127.0.0.1:8000
```

---

## AI Studio Dashboard

Navigate to:

```bash
cd C:\Users\ADMIN\Desktop\recovery\revenue-recovery-engine-ai-studio
```

Install dependencies:

```bash
npm install
```

Start the dashboard:

```bash
npm run dev
```

Dashboard:

```text
http://localhost:3000
```

---

# Validation

## Frontend

Run lint/type validation:

```bash
npm run lint
```

Build the dashboard:

```bash
npm run build
```

## Backend

Verify the following endpoints:

```text
GET  /health
POST /decide
GET  /audit/{transaction_id}
POST /report/email
```

---

# Known Limitations

This project is a **proof of concept**, not a production deployment.

Current limitations include:

- The core development/evaluation workflow uses synthetic data.
- Some supported actions are not naturally selected under the tested live scenarios.
- The audit trail is persistent and queryable but is not cryptographically immutable.
- Production readiness has not been established.
- Gmail delivery depends on valid SMTP configuration and network availability.

These limitations are explicitly documented as part of the project evidence.

---

# Conclusion

The **AI Revenue Recovery Decision Engine** demonstrates an end-to-end approach to intelligent revenue and payment recovery.

It combines:

```text
Machine Learning
        +
Expected Economic Value
        +
Deterministic Policy
        +
Communication Safety
        +
Persistent Auditability
        +
Real FastAPI Backend
        +
AI Studio Dashboard
        +
Operational Gmail Reporting
```

The final system can:

1. Accept a revenue-at-risk transaction context.
2. Determine eligible recovery actions.
3. Estimate action-conditional recovery probabilities.
4. Evaluate permitted actions economically.
5. Apply deterministic safety and policy constraints.
6. Select the best permitted recovery action.
7. Generate communication and fallback information.
8. Persist the decision in an audit trail.
9. Display the result through the AI Studio dashboard.
10. Retrieve the corresponding audit record.
11. Send the complete decision report through Gmail.

This demonstrates a **transparent, policy-constrained, auditable revenue recovery decision workflow** rather than an isolated machine-learning model.

---

# Project Status

| Component | Status |
|---|:---:|
| M1–M11 | ✅ **COMPLETE** |
| Machine Learning Decision Engine | ✅ **COMPLETE** |
| Policy-Constrained Optimization | ✅ **COMPLETE** |
| Persistent Audit Trail | ✅ **VERIFIED** |
| FastAPI Backend | ✅ **VERIFIED** |
| AI Studio Dashboard | ✅ **VERIFIED** |
| Gmail Decision Report | ✅ **VERIFIED** |
| End-to-End Proof of Concept | ✅ **COMPLETE** |

> **Final Status: AI Revenue Recovery Decision Engine — Complete Proof of Concept**
