import modal
import os
import json

# Image Definition: vLLM is critical for DeepSeek-OCR
image = (
    modal.Image.debian_slim()
    .pip_install("vllm>=0.6.3", "transformers", "numpy", "Pillow", "requests", "docling", "instructor")
)

app = modal.App("sarah-ai-worker", image=image)

@app.cls(gpu="A10G", container_idle_timeout=300)
class SchemaBasedProcessor:
    @modal.enter()
    def load_model(self):
        from vllm import LLM
        # Use the OCR-SPECIALIZED model (not Janus-Pro)
        self.llm = LLM(
            model="deepseek-ai/DeepSeek-OCR",
            trust_remote_code=True,
            enforce_eager=True
        )

    @modal.method()
    def process(self, r2_url, schema_json_str):
        from vllm import SamplingParams
        import re

        # Parse the schema
        schema = json.loads(schema_json_str)

        # Generate a prompt based on the user's schema
        prompt_parts = ["<image>\n<|grounding|>Extract the following information from the document:"]
        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')
            prompt_parts.append(f"- {field_name} ({field_type}): {instruction}")

        prompt_text = "\n".join(prompt_parts)

        sampling_params = SamplingParams(max_tokens=4096, temperature=0.1)

        # In production, you download r2_url to local bytes first
        # This is simplified vLLM usage:
        outputs = self.llm.generate(
            {"prompt": prompt_text, "multi_modal_data": {"image": r2_url}},
            sampling_params
        )

        extracted_text = outputs[0].outputs[0].text

        # Parse the extracted information according to the schema
        extracted_data = self.parse_extraction(extracted_text, schema)

        # Calculate confidence based on how many fields were successfully extracted
        confidence = len([k for k, v in extracted_data.items() if v]) / len(schema)

        return {
            "result": extracted_data,
            "confidence": confidence,
            "raw_extraction": extracted_text
        }

    def parse_extraction(self, extracted_text, schema):
        """
        Parse the extracted text according to the user's schema
        """
        result = {}

        for field in schema:
            field_name = field['name']
            field_type = field.get('type', 'text')
            instruction = field.get('instruction', '')

            # Look for the field in the extracted text
            if field_type == 'currency':
                # Extract currency values
                pattern = r'\$?[\d,]+\.?\d*'
                matches = re.findall(pattern, extracted_text)
                if matches:
                    result[field_name] = matches[0].replace(',', '')
                else:
                    result[field_name] = None
            elif field_type == 'number':
                # Extract numeric values
                pattern = r'\b\d+\.?\d*\b'
                matches = re.findall(pattern, extracted_text)
                if matches:
                    result[field_name] = matches[0]
                else:
                    result[field_name] = None
            elif field_type == 'date':
                # Extract date values
                date_patterns = [
                    r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',  # MM/DD/YYYY or MM/DD/YY
                    r'\b\d{4}-\d{2}-\d{2}\b',         # YYYY-MM-DD
                    r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',  # MM-DD-YYYY or MM-DD-YY
                ]
                for pattern in date_patterns:
                    matches = re.findall(pattern, extracted_text)
                    if matches:
                        result[field_name] = matches[0]
                        break
                else:
                    result[field_name] = None
            elif field_type == 'text':
                # Extract text based on the field name or instruction
                # Look for the field name followed by a colon and the value
                pattern = re.compile(re.escape(field_name) + r'\s*[:\-\—]\s*([^\n\r.]+)', re.IGNORECASE)
                match = pattern.search(extracted_text)

                if match:
                    result[field_name] = match.group(1).strip()
                else:
                    # If not found, try to find the instruction text
                    words = instruction.lower().split()
                    lines = extracted_text.split('\n')

                    for line in lines:
                        line_lower = line.lower()
                        if all(word in line_lower for word in words):
                            result[field_name] = line.strip()
                            break
                    else:
                        result[field_name] = None

        return result

# Queue Consumer (HTTP Pull Emulation or Direct Call)
@app.function(schedule=modal.Period(seconds=5), secrets=[modal.Secret.from_name("sarah-ai-secrets")])
def poll_queue():
    import requests
    import json

    # 1. Pull from Cloudflare Queue via API
    # In a real implementation, you would use the Cloudflare Queue API to pull messages
    # For now, we'll simulate this with a placeholder

    # Example of how this might work:
    # queue_url = os.environ.get("CLOUDFLARE_QUEUE_URL")
    # response = requests.get(queue_url, headers={"Authorization": f"Bearer {os.environ.get('CF_API_TOKEN')}"})
    # messages = response.json().get("messages", [])

    # 2. Process each message
    # for message in messages:
    #     payload = json.loads(message["payload"])
    #     result = SchemaBasedProcessor().process.remote(
    #         payload["r2_url"],
    #         payload["schema_json"]
    #     )
    #
    #     # 3. Post back to main API with header x-internal-secret
    #     callback_response = requests.post(
    #         f"{payload['api_url']}/webhook/internal/complete",
    #         headers={"x-internal-secret": os.environ.get("INTERNAL_SECRET")},
    #         json={
    #             "job_id": payload["job_id"],
    #             "status": "completed",
    #             "result": result["result"],
    #             "confidence": result["confidence"]
    #         }
    #     )
    pass