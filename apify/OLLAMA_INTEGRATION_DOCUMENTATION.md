# Sarah AI - Apify Implementation with Ollama Integration

## Overview

This document describes the implementation of Sarah AI using the Apify platform with local Ollama models for cost-effective processing. The system transforms email attachments into structured data based on user-defined schemas.

## Architecture

### Components
- **Apify Actor**: Processes documents using local Ollama models
- **Granite Docling**: Efficient ONNX-based document processing (replaces DeepSeek OCR for cost efficiency)
- **Ministral-3:3b**: Local LLM for schema-based extraction
- **Cloudflare Workers**: Email ingestion and webhook handling
- **Cloudflare D1**: Database for users, blueprints, and jobs
- **Cloudflare R2**: Document storage

### Data Flow
1. Email arrives at user's inbox alias (e.g., `uuid@sarah.ai`)
2. Cloudflare worker extracts PDF attachment
3. Document uploaded to R2 storage
4. Apify actor triggered with R2 URL and user schema
5. Docling processes document to extract text/content
6. Ministral LLM extracts fields based on user schema
7. Results validated and confidence calculated
8. Webhook sent back to Cloudflare with results
9. Data stored in database and optionally sent to target sheet

## Configuration

### Environment Variables
```bash
# Ollama Configuration
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
EXTRACTION_MODEL=ministral-3:3b

# Document Processing
DOCLING_MODEL=ibm/granite-docling:latest

# Processing Configuration
PROCESSING_TIMEOUT=300  # 5 minutes timeout
MAX_FILE_SIZE=10485760  # 10MB in bytes
```

### Required Models
- `ministral-3:3b` - for schema-based extraction
- `ibm/granite-docling:latest` - for document processing

## Implementation Details

### 1. Schema-Based Extraction
Users define custom extraction schemas with:
- Field names
- Field types (text, currency, number, date)
- Instructions for extraction

### 2. Validation & Confidence Scoring
- Confidence calculated based on field extraction success rate
- Low-confidence results flagged for review
- Validation checks ensure data quality

### 3. Cost Optimization
- Uses efficient ONNX-based Docling for document processing
- Local Ollama models eliminate API costs
- Only essential models used (no redundant processing)

## Key Changes from Original Implementation

1. **Model Selection**: Replaced DeepSeek OCR with Granite Docling for cost efficiency
2. **Local Processing**: All AI processing happens on local Ollama instance
3. **Simplified Architecture**: Removed redundant OCR processing, streamlined to single efficient pipeline
4. **Cost Optimization**: Reduced compute requirements by using efficient ONNX models

## API Endpoints

### Apify Actor Input
```json
{
  "pdf_url": "https://r2.domain.com/path/to/document.pdf",
  "schema": [
    {
      "name": "Vendor",
      "type": "text", 
      "instruction": "Extract vendor name"
    },
    {
      "name": "Total",
      "type": "currency",
      "instruction": "Extract total amount including tax"
    }
  ],
  "webhookUrl": "https://api.sarah.ai/webhook/apify-result"
}
```

### Apify Actor Output
```json
{
  "extracted_data": {
    "Vendor": "Home Depot",
    "Total": "$105.50",
    "Invoice Date": "2025-12-26"
  },
  "confidence": 0.95,
  "validation_status": "valid",
  "raw_text": "Raw document text...",
  "processing_timestamp": "2025-12-26T12:00:00.000Z"
}
```

## Deployment

1. Pull required Ollama models:
   ```bash
   ollama pull ministral-3:3b
   ollama pull ibm/granite-docling:latest
   ```

2. Set environment variables appropriately

3. Deploy Apify actor:
   ```bash
   cd apify
   apify push
   ```

4. Configure Cloudflare workers to call the deployed actor

## Benefits

- **Cost Effective**: Local processing eliminates API costs
- **Efficient**: Uses ONNX models for optimal performance
- **Flexible**: Schema-based extraction adapts to any document type
- **Reliable**: Confidence scoring flags uncertain extractions
- **Scalable**: Apify platform handles scaling automatically