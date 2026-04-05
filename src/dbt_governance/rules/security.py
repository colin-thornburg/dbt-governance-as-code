"""Security and data governance rules — PII handling, credential hygiene, access policy."""

from __future__ import annotations

import re

from dbt_governance.config import Severity
from dbt_governance.rules.base import BaseRule, RuleContext, Violation, register_rule

# Column names that indicate personally identifiable / sensitive data
_PII_COLUMN_KEYWORDS = {
    "email", "email_address", "email_addr",
    "phone", "phone_number", "mobile", "mobile_number", "cell_phone",
    "ssn", "social_security", "social_security_number", "sin",
    "dob", "date_of_birth", "birth_date", "birthdate",
    "address", "street_address", "mailing_address", "billing_address", "home_address",
    "ip_address", "ip_addr",
    "credit_card", "card_number", "ccn", "cvv", "pan",
    "passport", "passport_number",
    "national_id", "drivers_license", "license_number",
    "salary", "compensation", "wage", "income",
    "health_record", "diagnosis", "medication",
}

# Tags that indicate proper PII handling is in place
_PII_TAGS = {"pii", "phi", "pci", "sensitive", "restricted", "confidential", "gdpr", "personal", "personal_data"}

# Regex patterns that indicate hardcoded credentials in SQL
_CRED_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"][^'\"]{4,}['\"]"),
    re.compile(r"(?i)(api_key|apikey|api_secret|secret_key|access_key|private_key)\s*[=:]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)(auth_token|bearer_token|access_token|refresh_token)\s*[=:]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"AKIA[0-9A-Z]{16}"),                             # AWS IAM access key
    re.compile(r"(?i)jdbc:[^'\"\s]+password=[^&'\"\s;]{4,}"),   # JDBC connection string
]


def _column_is_pii(col_name: str) -> bool:
    """Return True if the column name strongly suggests PII/sensitive data."""
    name = col_name.lower()
    # Exact match
    if name in _PII_COLUMN_KEYWORDS:
        return True
    # Suffix/prefix match for common patterns (e.g., customer_email, user_phone_number)
    for kw in _PII_COLUMN_KEYWORDS:
        if name.endswith(f"_{kw}") or name.startswith(f"{kw}_"):
            return True
    return False


@register_rule
class PiiColumnsTaggedRule(BaseRule):
    rule_id = "security.pii_columns_tagged"
    category = "security"
    description = "Models with PII-sounding column names must have a pii or sensitive tag"
    default_severity = Severity.WARNING

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue

            pii_cols = [col for col in model.columns if _column_is_pii(col)]
            if not pii_cols:
                continue

            model_tags_lower = {t.lower() for t in model.tags}
            has_pii_tag = bool(model_tags_lower & _PII_TAGS)
            if not has_pii_tag:
                cols_display = ", ".join(pii_cols[:5])
                if len(pii_cols) > 5:
                    cols_display += f" (+{len(pii_cols) - 5} more)"
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Model '{model.name}' has PII-sounding columns ({cols_display}) "
                        f"but no pii/sensitive tag"
                    ),
                    suggestion=(
                        "Add a 'pii' or 'sensitive' tag to the model config: "
                        "{{ config(tags=['pii']) }}. This enables lineage-aware PII scanning and "
                        "access policy enforcement."
                    ),
                ))
        return violations


@register_rule
class NoHardcodedCredentialsRule(BaseRule):
    rule_id = "security.no_hardcoded_credentials"
    category = "security"
    description = "SQL must not contain hardcoded credentials, API keys, or connection strings"
    default_severity = Severity.ERROR

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        for model in context.manifest_data.models.values():
            if context.governance_config.is_path_excluded(model.file_path):
                continue
            code = model.raw_code or model.compiled_code
            if not code or code == "--placeholder--":
                continue

            matched_patterns: list[str] = []
            for pattern in _CRED_PATTERNS:
                m = pattern.search(code)
                if m:
                    # Redact the actual value from the violation message
                    snippet = m.group(0)[:40].rstrip()
                    matched_patterns.append(snippet + "…")

            if matched_patterns:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=model.name,
                    file_path=model.file_path,
                    message=(
                        f"Model '{model.name}' appears to contain hardcoded credentials "
                        f"({len(matched_patterns)} pattern(s) matched)"
                    ),
                    suggestion=(
                        "Move secrets to environment variables and reference them via "
                        "{{ env_var('MY_SECRET') }} in dbt. Never commit credentials to source control."
                    ),
                ))
        return violations


@register_rule
class PrivilegedAccessPolicyRule(BaseRule):
    rule_id = "security.privileged_access_policy"
    category = "security"
    description = "Sources with PII-sounding table names should have meta.data_classification defined"
    default_severity = Severity.INFO

    def evaluate(self, context: RuleContext) -> list[Violation]:
        severity = self.get_severity(context.governance_config)
        violations = []

        _PRIVILEGED_SOURCE_KEYWORDS = {
            "user", "users", "customer", "customers", "patient", "patients",
            "employee", "employees", "person", "people", "member", "members",
            "account", "accounts", "contact", "contacts",
            "payment", "payments", "transaction", "transactions",
            "order", "orders", "invoice", "invoices",
        }

        for source in context.manifest_data.sources.values():
            name_lower = source.name.lower()
            source_name_lower = source.source_name.lower()

            is_privileged = any(
                kw in name_lower or kw in source_name_lower
                for kw in _PRIVILEGED_SOURCE_KEYWORDS
            )
            if not is_privileged:
                continue

            has_classification = (
                source.meta.get("data_classification")
                or source.meta.get("access_policy")
                or source.meta.get("sensitivity")
                or source.meta.get("pii")
            )
            if not has_classification:
                violations.append(Violation(
                    rule_id=self.rule_id,
                    severity=severity,
                    model_name=f"{source.source_name}.{source.name}",
                    file_path="",
                    message=(
                        f"Source '{source.source_name}.{source.name}' appears to contain "
                        f"user or transactional data but has no data_classification defined"
                    ),
                    suggestion=(
                        "Add meta.data_classification (e.g., 'pii', 'sensitive', 'internal') "
                        "to the source definition in sources.yml. This enables audit trails, "
                        "access policy automation, and accelerates security review."
                    ),
                ))
        return violations
