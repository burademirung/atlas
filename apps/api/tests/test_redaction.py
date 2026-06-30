import logging

from atlas_api.security.redaction import (
    CC_TOKEN,
    EMAIL_TOKEN,
    PHONE_TOKEN,
    SSN_TOKEN,
    RedactionFilter,
    redact_pii,
)


def test_redacts_ssn_dashed_and_spaced() -> None:
    assert redact_pii("my ssn is 123-45-6789 ok") == f"my ssn is {SSN_TOKEN} ok"
    assert redact_pii("ssn 123 45 6789") == f"ssn {SSN_TOKEN}"


def test_redacts_email() -> None:
    assert redact_pii("reach me at Jane.Doe+x@example.co.uk now") == (
        f"reach me at {EMAIL_TOKEN} now"
    )


def test_redacts_phone() -> None:
    assert redact_pii("call +1 (415) 555-0132 please") == f"call {PHONE_TOKEN} please"
    assert redact_pii("415-555-0132") == PHONE_TOKEN


def test_redacts_valid_luhn_card_but_not_random_digits() -> None:
    # 4111 1111 1111 1111 is a canonical Luhn-valid test card.
    assert redact_pii("card 4111 1111 1111 1111 leaked") == f"card {CC_TOKEN} leaked"
    # A 16-digit run that fails Luhn is left intact (precision over recall).
    assert "1234567890123456" in redact_pii("ref 1234567890123456")


def test_email_digits_not_reparsed_as_ssn() -> None:
    out = redact_pii("user123-45-6789@example.com")
    assert out == EMAIL_TOKEN


def test_empty_and_clean_text_unchanged() -> None:
    assert redact_pii("") == ""
    assert redact_pii("nothing sensitive here") == "nothing sensitive here"


def test_multiple_pii_in_one_string() -> None:
    out = redact_pii("SSN 123-45-6789, card 4111111111111111, mail a@b.com")
    assert SSN_TOKEN in out
    assert CC_TOKEN in out
    assert EMAIL_TOKEN in out
    assert "123-45-6789" not in out


def test_logging_filter_scrubs_record() -> None:
    flt = RedactionFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="leaked ssn 123-45-6789 for user",
        args=(),
        exc_info=None,
    )
    assert flt.filter(record) is True
    assert "123-45-6789" not in record.getMessage()
    assert SSN_TOKEN in record.getMessage()


def test_logging_filter_handles_args_interpolation() -> None:
    flt = RedactionFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="contact %s",
        args=("a@b.com",),
        exc_info=None,
    )
    assert flt.filter(record) is True
    assert record.getMessage() == f"contact {EMAIL_TOKEN}"


def test_logging_filter_passes_clean_record_untouched() -> None:
    flt = RedactionFilter()
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="all good %s",
        args=("here",),
        exc_info=None,
    )
    assert flt.filter(record) is True
    assert record.getMessage() == "all good here"
