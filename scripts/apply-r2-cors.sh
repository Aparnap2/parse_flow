#!/bin/bash

# Apply R2 CORS policy for DocuFlow
# This script sets up CORS for the R2 bucket to allow cross-origin requests

echo '[
  {
    "AllowedOrigins": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"]
  }
]' > cors.json

echo "Applying CORS policy to R2 bucket 'docuflow-storage'..."
wrangler r2 bucket put-cors docuflow-storage --file cors.json

# Clean up
rm cors.json

echo "R2 CORS policy applied successfully!"