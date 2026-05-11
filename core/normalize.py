from core.output_validator import quality_ceiling, validate_enhance_result


def normalize_result(result: dict, raw_prompt: str = "") -> dict:
    """Backward-compatible wrapper for older imports."""
    return validate_enhance_result(result, raw_prompt=raw_prompt)
