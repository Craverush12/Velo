import tempfile
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from markitdown import MarkItDown

router = APIRouter()

class ExtractHtmlRequest(BaseModel):
    html: str

@router.post("/html")
async def extract_html(request: ExtractHtmlRequest):
    try:
        md = MarkItDown()
        
        # Write HTML to a temporary file since markitdown operates on files
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as temp_file:
            temp_file.write(request.html)
            temp_path = temp_file.name

        try:
            # Convert using markitdown
            result = md.convert(temp_path)
            return {"status": "success", "markdown": result.text_content}
        finally:
            # Clean up the temp file
            if os.path.exists(temp_path):
                os.unlink(temp_path)
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to extract HTML using markitdown: {str(e)}")
