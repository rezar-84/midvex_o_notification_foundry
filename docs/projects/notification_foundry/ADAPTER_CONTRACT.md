# Adapter Contract — Notification Foundry

## Purpose

Channel modules must implement a common adapter contract so the foundry can orchestrate shared delivery, retry, and logging workflows.

## Channel adapter responsibilities

A channel adapter translates between foundry normalized DTOs and the channel's API payloads/responses.

Channel adapters should not own common Odoo business workflows (queueing, retry, logging, permissions).

## Conceptual Python interface

```python
class NotificationAdapter:
    channel_code = None

    def test_connection(self, account):
        raise NotImplementedError

    def send(self, account, message_dto):
        raise NotImplementedError

    def register_webhook(self, account, webhook_url, secret_token):
        raise NotImplementedError

    def parse_inbound(self, raw_payload):
        raise NotImplementedError

    def parse_error(self, response_or_exception):
        raise NotImplementedError
```

## Normalized message DTO

```json
{
  "message_id": 0,
  "recipient_external_id": "chat-or-address",
  "subject": "Subject line (if applicable)",
  "body": "Rendered message body",
  "template_code": "lead_created",
  "res_model": "crm.lead",
  "res_id": 0,
  "variables": {}
}
```

## Normalized delivery result DTO

```json
{
  "provider_message_id": "external-id",
  "status": "sent",
  "delivered_at": "2026-08-01T12:00:00+00:00",
  "raw": {}
}
```

## Normalized inbound event DTO

```json
{
  "external_id": "chat-id",
  "external_username": "username",
  "text": "/link ABC123",
  "command": "link",
  "command_args": "ABC123",
  "received_at": "2026-08-01T12:00:00+00:00",
  "raw": {}
}
```

## Error contract

```json
{
  "error_code": "RATE_LIMIT",
  "message": "Readable message",
  "retryable": true,
  "retry_after_seconds": 300,
  "raw_reference": "channel-request-id"
}
```

## Pagination contract

```json
{
  "items": [],
  "next_page_token": null,
  "has_more": false
}
```
