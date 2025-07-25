import os
import re
import aiohttp
import shutil
import uuid
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List
import easyocr

# Init FastAPI and OCR reader
app = FastAPI()
reader = easyocr.Reader(['en'])

# ✅ Add CORS middleware after app initialization
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # For development; restrict to frontend domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = "./receipts"
os.makedirs(TEMP_DIR, exist_ok=True)

# Request model
class ReceiptRequest(BaseModel):
    image_urls: List[str]
    branch_id: str
    date: str

# Price extraction
def extract_total_from_image(path):
    result = reader.readtext(path)
    probable_total = 0.0
    price_pattern = re.compile(r'(total\s*[:\-]?\s*[\$RM]?\s?\d+\.\d{2}|[\$RM]?\s?\d+\.\d{2})', re.IGNORECASE)

    for (_, text, prob) in result:
        if prob >= 0.5:
            match = price_pattern.search(text.lower())
            if match:
                raw_price = re.findall(r'\d+\.\d{2}', match.group())
                if raw_price:
                    amount = float(raw_price[0])
                    if amount > probable_total and amount > 1.0:
                        probable_total = amount
    return probable_total

# Helper: Download image
async def download_image(session, url, dest_path):
    async with session.get(url) as resp:
        if resp.status != 200:
            raise Exception(f"Failed to download {url}")
        with open(dest_path, 'wb') as f:
            f.write(await resp.read())

@app.post("/process-receipts")
async def process_receipts(data: ReceiptRequest):
    totals = []
    try:
        async with aiohttp.ClientSession() as session:
            for url in data.image_urls:
                filename = f"{uuid.uuid4()}.jpg"
                filepath = os.path.join(TEMP_DIR, filename)
                await download_image(session, url, filepath)

                try:
                    total = extract_total_from_image(filepath)
                    totals.append(round(total, 2))
                except Exception as e:
                    totals.append(0.0)

                os.remove(filepath)

        return {
            "total_amount": round(sum(totals), 2),
            "individual_amounts": totals,
            "success": True,
            "processed_count": len(totals)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR Failed: {str(e)}")
@app.get("/")
def index():
    return {"message": "Receipt OCR is live!"}
