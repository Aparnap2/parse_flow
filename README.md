# Structurize - Invoice Processing Automation

Structurize is an automated invoice processing system that transforms email attachments into structured data in Google Sheets. The system processes invoice PDFs sent to personalized email addresses and automatically populates designated Google Sheets with extracted data.

## Architecture

The system consists of multiple Cloudflare Workers and a Python processing engine:

- **Email Worker**: Receives email attachments and queues processing jobs
- **Engine**: AI-powered PDF processing and data extraction
- **Sync Worker**: Processes extracted data, performs audits, and updates Google Sheets
- **Billing Worker**: Handles subscription management via Lemon Squeezy
- **Pages**: Web dashboard for users to manage their account and view jobs

## Features

- **Email-to-Sheet Pipeline**: Forward invoice PDFs to your personalized email address → automatic data extraction → Google Sheets population
- **AI-Powered Extraction**: Advanced language models extract vendor, date, total, invoice number, and line items
- **Data Validation & Audit**: Multi-layer validation including math verification, duplicate detection, and anomaly detection
- **Subscription Management**: Integrated billing with Lemon Squeezy
- **Demo Flow**: Special handling for demo@structurize.ai to showcase the service
- **Secure Document Processing**: Direct R2 access for document retrieval

## Components

### Email Worker
- Receives emails with PDF attachments
- Stores documents in R2 storage
- Calls processing engine
- Queues jobs for sync processing
- Special handling for demo@structurize.ai

### Processing Engine
- AI-powered PDF parsing and data extraction
- Extracts vendor, date, total, invoice number, and line items
- Generates visual proof for validation
- Configurable AI model settings

### Sync Worker
- Processes extracted data from jobs queue
- Performs validation and audit checks
- Updates Google Sheets with validated data
- Stores historical records
- Implements retry logic and dead-letter handling

### Billing Worker
- Handles Lemon Squeezy webhooks with signature verification
- Manages user subscription plans
- Supports multiple product tiers

### Dashboard (Pages)
- User dashboard to view processing jobs
- Shows job status and audit results
- Displays user subscription information

## Configuration

### Environment Variables

#### Email Worker
- `ENGINE_URL`: URL of the processing engine
- `ENGINE_SECRET`: Secret for authenticating with engine
- `R2_PUBLIC_URL`: Public URL for R2 bucket

#### Sync Worker
- `DEMO_SHEET_REFRESH_TOKEN`: Refresh token for demo sheet access
- `DEMO_SPREADSHEET_ID`: ID of the demo spreadsheet
- `EMAIL_SERVICE_URL`: URL for sending notification emails

#### Billing Worker
- `LEMONSQEEZY_SECRET`: Lemon Squeezy API secret
- `LEMON_STARTER_PRODUCT_ID`: Product ID for starter plan
- `LEMON_PRO_PRODUCT_ID`: Product ID for pro plan
- `LEMONSQEEZY_STORE_ID`: Lemon Squeezy store ID

#### Engine
- `ENGINE_SECRET`: Secret for authenticating requests
- `R2_ACCESS_KEY`: R2 access key
- `R2_SECRET_KEY`: R2 secret key
- `R2_ENDPOINT`: R2 endpoint URL
- `R2_PUBLIC_URL`: Public R2 URL
- `LANGEXTRACT_MODEL_ID`: AI model to use (default: gemini-2.5-flash)
- `LANGEXTRACT_PASSES`: Number of extraction passes (default: 2)
- `LANGEXTRACT_MAX_WORKERS`: Max concurrent workers (default: 4)

## Setup & Deployment

See [DEPLOYMENT_COMMANDS.md](DEPLOYMENT_COMMANDS.md) for detailed deployment instructions.

## Security

- Lemon Squeezy webhook signature verification
- API authentication with secrets
- User isolation in data access
- Secure R2 document access

## Development

The system is designed with microservices architecture for scalability and maintainability. Each component can be developed and deployed independently.

## License

[Specify license here]