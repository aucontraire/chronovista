"""Unit tests for API response schemas."""
import pytest
from pydantic import ValidationError


class TestPaginationMeta:
    """Tests for PaginationMeta schema."""

    def test_pagination_meta_creation(self) -> None:
        """Test creating a valid PaginationMeta instance."""
        from chronovista.api.schemas.responses import PaginationMeta

        pagination = PaginationMeta(
            total=100,
            limit=20,
            offset=0,
            has_more=True,
        )

        assert pagination.total == 100
        assert pagination.limit == 20
        assert pagination.offset == 0
        assert pagination.has_more is True

    def test_pagination_meta_has_more_false(self) -> None:
        """Test PaginationMeta with has_more=False."""
        from chronovista.api.schemas.responses import PaginationMeta

        pagination = PaginationMeta(
            total=100,
            limit=20,
            offset=80,
            has_more=False,
        )

        assert pagination.has_more is False

    def test_pagination_meta_requires_all_fields(self) -> None:
        """Test PaginationMeta requires all fields."""
        from chronovista.api.schemas.responses import PaginationMeta

        with pytest.raises(ValidationError) as exc_info:
            PaginationMeta(total=100, limit=20)  # Missing offset and has_more

        errors = exc_info.value.errors()
        assert len(errors) == 2
        assert any(e["loc"] == ("offset",) for e in errors)
        assert any(e["loc"] == ("has_more",) for e in errors)

    def test_pagination_meta_strict_types(self) -> None:
        """Test PaginationMeta enforces strict types."""
        from chronovista.api.schemas.responses import PaginationMeta

        # String instead of int should fail with strict=True
        with pytest.raises(ValidationError):
            PaginationMeta(
                total="100",  # Should be int
                limit=20,
                offset=0,
                has_more=True,
            )


class TestApiError:
    """Tests for ApiError schema."""

    def test_api_error_creation(self) -> None:
        """Test creating a valid ApiError instance."""
        from chronovista.api.schemas.responses import ApiError

        error = ApiError(
            code="NOT_FOUND",
            message="Resource not found",
        )

        assert error.code == "NOT_FOUND"
        assert error.message == "Resource not found"
        assert error.details is None

    def test_api_error_with_details(self) -> None:
        """Test ApiError with optional details."""
        from chronovista.api.schemas.responses import ApiError

        error = ApiError(
            code="VALIDATION_ERROR",
            message="Invalid input",
            details={"field": "email", "reason": "Invalid format"},
        )

        assert error.code == "VALIDATION_ERROR"
        assert error.message == "Invalid input"
        assert error.details == {"field": "email", "reason": "Invalid format"}

    def test_api_error_requires_code_and_message(self) -> None:
        """Test ApiError requires code and message."""
        from chronovista.api.schemas.responses import ApiError

        with pytest.raises(ValidationError) as exc_info:
            ApiError(code="NOT_FOUND")  # Missing message

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("message",)

    def test_api_error_strict_types(self) -> None:
        """Test ApiError enforces strict types."""
        from chronovista.api.schemas.responses import ApiError

        # Integer instead of string should fail with strict=True
        with pytest.raises(ValidationError):
            ApiError(
                code=404,  # Should be string
                message="Not found",
            )


class TestApiResponse:
    """Tests for ApiResponse schema."""

    def test_api_response_with_dict_data(self) -> None:
        """Test ApiResponse with dictionary data."""
        from chronovista.api.schemas.responses import ApiResponse

        response = ApiResponse(data={"status": "ok", "count": 42})

        assert response.data == {"status": "ok", "count": 42}
        assert response.pagination is None

    def test_api_response_with_list_data(self) -> None:
        """Test ApiResponse with list data."""
        from chronovista.api.schemas.responses import ApiResponse

        response = ApiResponse(data=[1, 2, 3, 4, 5])

        assert response.data == [1, 2, 3, 4, 5]
        assert response.pagination is None

    def test_api_response_with_pagination(self) -> None:
        """Test ApiResponse with pagination metadata."""
        from chronovista.api.schemas.responses import ApiResponse, PaginationMeta

        pagination = PaginationMeta(
            total=100,
            limit=20,
            offset=0,
            has_more=True,
        )

        response = ApiResponse(data=["item1", "item2"], pagination=pagination)

        assert response.data == ["item1", "item2"]
        assert response.pagination is not None
        assert response.pagination.total == 100
        assert response.pagination.limit == 20

    def test_api_response_generic_type_with_custom_model(self) -> None:
        """Test ApiResponse works with custom Pydantic models."""
        from pydantic import BaseModel

        from chronovista.api.schemas.responses import ApiResponse

        class CustomData(BaseModel):
            name: str
            value: int

        custom_data = CustomData(name="test", value=42)
        response = ApiResponse(data=custom_data)

        assert response.data.name == "test"
        assert response.data.value == 42

    def test_api_response_requires_data(self) -> None:
        """Test ApiResponse requires data field."""
        from chronovista.api.schemas.responses import ApiResponse

        with pytest.raises(ValidationError) as exc_info:
            ApiResponse()  # Missing data

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("data",)


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_error_response_creation(self) -> None:
        """Test creating a valid ErrorResponse instance."""
        from chronovista.api.schemas.responses import ApiError, ErrorResponse

        api_error = ApiError(
            code="NOT_FOUND",
            message="Resource not found",
        )

        error_response = ErrorResponse(error=api_error)

        assert error_response.error.code == "NOT_FOUND"
        assert error_response.error.message == "Resource not found"

    def test_error_response_with_error_details(self) -> None:
        """Test ErrorResponse with error details."""
        from chronovista.api.schemas.responses import ApiError, ErrorResponse

        api_error = ApiError(
            code="VALIDATION_ERROR",
            message="Invalid input",
            details={"field": "email"},
        )

        error_response = ErrorResponse(error=api_error)

        assert error_response.error.code == "VALIDATION_ERROR"
        assert error_response.error.details == {"field": "email"}

    def test_error_response_requires_error(self) -> None:
        """Test ErrorResponse requires error field."""
        from chronovista.api.schemas.responses import ErrorResponse

        with pytest.raises(ValidationError) as exc_info:
            ErrorResponse()  # Missing error

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"] == ("error",)

    def test_error_response_strict_types(self) -> None:
        """Test ErrorResponse enforces strict types for error field."""
        from chronovista.api.schemas.responses import ErrorResponse

        # String instead of ApiError should fail with strict=True
        with pytest.raises(ValidationError):
            ErrorResponse(error="error message")  # Should be ApiError instance


class TestSchemaIntegration:
    """Integration tests for schema combinations."""

    def test_api_response_json_serialization(self) -> None:
        """Test ApiResponse can be serialized to JSON."""
        from chronovista.api.schemas.responses import ApiResponse, PaginationMeta

        pagination = PaginationMeta(
            total=100,
            limit=20,
            offset=0,
            has_more=True,
        )

        response = ApiResponse(
            data={"status": "ok", "items": [1, 2, 3]}, pagination=pagination
        )

        json_data = response.model_dump()

        assert json_data["data"] == {"status": "ok", "items": [1, 2, 3]}
        assert json_data["pagination"]["total"] == 100
        assert json_data["pagination"]["limit"] == 20

    def test_error_response_json_serialization(self) -> None:
        """Test ErrorResponse can be serialized to JSON."""
        from chronovista.api.schemas.responses import ApiError, ErrorResponse

        api_error = ApiError(
            code="NOT_FOUND",
            message="Resource not found",
            details={"resource_id": "123"},
        )

        error_response = ErrorResponse(error=api_error)
        json_data = error_response.model_dump()

        assert json_data["error"]["code"] == "NOT_FOUND"
        assert json_data["error"]["message"] == "Resource not found"
        assert json_data["error"]["details"]["resource_id"] == "123"

    def test_nested_api_response_serialization(self) -> None:
        """Test ApiResponse with nested data structures."""
        from chronovista.api.schemas.responses import ApiResponse

        complex_data = {
            "user": {"id": 1, "name": "Test User"},
            "videos": [
                {"id": "v1", "title": "Video 1"},
                {"id": "v2", "title": "Video 2"},
            ],
        }

        response = ApiResponse(data=complex_data)
        json_data = response.model_dump()

        assert json_data["data"]["user"]["name"] == "Test User"
        assert len(json_data["data"]["videos"]) == 2
        assert json_data["data"]["videos"][0]["title"] == "Video 1"
