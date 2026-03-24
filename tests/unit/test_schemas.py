"""Tests for Pydantic schema validation."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.document import (
    AnonymizeResponse,
    DetectionResponse,
    DocumentPreviewResponse,
    FeedbackItem,
    HumanFeedbackResponse,
    ValidateDocumentRequest,
)


class TestDetectionResponse:
    def test_valid_detection(self):
        d = DetectionResponse(
            entity_type="PERSON",
            start_index=0,
            end_index=5,
            value_excerpt="hello",
            replacement="[PERSON]",
        )
        assert d.entity_type == "PERSON"

    def test_negative_index_rejected(self):
        with pytest.raises(ValidationError):
            DetectionResponse(
                entity_type="PERSON",
                start_index=-1,
                end_index=5,
                value_excerpt="hello",
                replacement="[PERSON]",
            )

    def test_end_before_start_rejected(self):
        with pytest.raises(ValidationError):
            DetectionResponse(
                entity_type="PERSON",
                start_index=10,
                end_index=5,
                value_excerpt="hello",
                replacement="[PERSON]",
            )


class TestFeedbackItem:
    def test_valid_missed_entity(self):
        f = FeedbackItem(
            feedback_type="missed_entity",
            entity_type="SIRET",
        )
        assert f.feedback_type == "missed_entity"

    def test_missed_entity_requires_entity_type(self):
        with pytest.raises(ValidationError, match="entity_type"):
            FeedbackItem(feedback_type="missed_entity")

    def test_wrong_entity_type_requires_labels(self):
        with pytest.raises(ValidationError, match="original_label"):
            FeedbackItem(feedback_type="wrong_entity_type")

    def test_wrong_entity_type_valid(self):
        f = FeedbackItem(
            feedback_type="wrong_entity_type",
            original_label="PERSON",
            corrected_label="COMPANY",
        )
        assert f.corrected_label == "COMPANY"

    def test_field_correction_requires_hash(self):
        with pytest.raises(ValidationError, match="corrected_value_hash"):
            FeedbackItem(feedback_type="field_correction")

    def test_field_correction_valid(self):
        f = FeedbackItem(
            feedback_type="field_correction",
            corrected_value_hash="abc123" * 10 + "abcd",
        )
        assert f.feedback_type == "field_correction"

    def test_false_positive_no_extra_required(self):
        f = FeedbackItem(feedback_type="false_positive")
        assert f.entity_type is None

    def test_review_comment_max_length(self):
        with pytest.raises(ValidationError):
            FeedbackItem(
                feedback_type="false_positive",
                review_comment="x" * 2001,
            )

    def test_span_order_validated(self):
        with pytest.raises(ValidationError, match="source_span_end"):
            FeedbackItem(
                feedback_type="false_positive",
                source_span_start=10,
                source_span_end=5,
            )

    def test_invalid_feedback_type_rejected(self):
        with pytest.raises(ValidationError):
            FeedbackItem(feedback_type="not_a_valid_type")


class TestValidateDocumentRequest:
    def test_defaults(self):
        req = ValidateDocumentRequest()
        assert req.doc_type == "generic"
        assert req.profile_used == "dataset_accounting_pseudo"
        assert req.final_text is None
        assert req.feedbacks == []

    def test_with_feedbacks(self):
        req = ValidateDocumentRequest(
            doc_type="bilan",
            feedbacks=[
                FeedbackItem(feedback_type="false_positive"),
                FeedbackItem(feedback_type="missed_entity", entity_type="IBAN"),
            ],
        )
        assert len(req.feedbacks) == 2


class TestHumanFeedbackResponse:
    def test_response_fields(self):
        r = HumanFeedbackResponse(
            status="recorded",
            feedback_id="abc-123",
            feedback_type="missed_entity",
        )
        assert r.status == "recorded"
