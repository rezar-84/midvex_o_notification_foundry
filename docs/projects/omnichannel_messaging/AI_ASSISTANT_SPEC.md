# AI Assistant Specification

## Provenance

Merged from `varsco_omnichannel_messaging_project/12_AI_ASSISTANT_SPEC.md`. Phase 8–9 work; nothing here is implemented, and per ADR-007 nothing here may become a dependency of message transport.

## Purpose

AI improves language coverage and agent efficiency. It is not the source of truth and not the core transport.

## Modes

These map to `midvex.conversation.thread.ai_mode`.

### OFF
No AI processing except optional analytics explicitly configured.

### ASSIST
AI may:
- detect language;
- translate;
- summarize;
- classify intent;
- extract lead fields;
- propose reply.

Human approves outbound reply.

### AUTO
AI may automatically respond only for approved low-risk intents.

### HUMAN_TAKEOVER
AI stops automatic responses until explicitly re-enabled.

## Allowed auto-response scope

Examples:
- company information;
- office hours;
- basic product availability categories;
- approved product facts from Odoo/knowledge base;
- collecting contact details;
- collecting RFQ details;
- basic acknowledgement;
- routing questions.

## Mandatory human handoff

Examples:
- pricing negotiation;
- discounts;
- binding quotation;
- complaints/escalation;
- payment dispute;
- legal/regulatory issue;
- technical advice outside approved knowledge;
- high-value lead rules;
- explicit human request;
- AI uncertainty above threshold.

## Language flow

Store:
- original text;
- detected language;
- translated text;
- target translation language.

Never replace original customer message.

## Knowledge source

Preferred source order:
1. Odoo structured product/business data;
2. approved company knowledge base;
3. approved technical documents;
4. general model knowledge only when safe and clearly non-authoritative.

## RAG/tool design

AI can call tightly scoped tools such as:
- `get_product_summary(product_id)`
- `search_approved_knowledge(query)`
- `get_company_contact_info(company_id)`
- `update_lead_qualification(fields)`
- `request_human_handoff(reason)`

Avoid generic unrestricted Odoo ORM access from the model.

## Lead extraction

Potential structured fields:
- product;
- quantity;
- country;
- delivery destination;
- species;
- farm type;
- timeline;
- company;
- email;
- preferred language.

All extracted fields must carry:
- source message IDs;
- confidence;
- whether human confirmed.

## AI audit

Store:
- mode;
- provider/model identifier if needed;
- generated flag;
- human approval;
- input references, not necessarily raw prompt;
- failure code.

## Offline behavior

Company config:
- staffed hours;
- timezone;
- AI auto enabled/disabled;
- approved intent set.

When offline:
- identify AI clearly where appropriate;
- collect enquiry;
- avoid promises about exact human response time unless configured;
- notify agent on return through normal workflow.
