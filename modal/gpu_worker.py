import modal
import os

# Image Definition: vLLM is critical for DeepSeek-OCR
image = (
    modal.Image.debian_slim()
    .pip_install("vllm>=0.6.3", "transformers", "numpy", "Pillow", "requests", "docling")
)

app = modal.App("parseflow-worker", image=image)

@app.cls(gpu="A10G", container_idle_timeout=300)
class DeepSeekProcessor:
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
    def process(self, r2_url, mode="general"):
        from vllm import SamplingParams

        # PROMPT: "grounding" enables bounding box / layout awareness
        prompt_text = "<image>\n<|grounding|>Convert the document to markdown." if mode == "financial" else "<image>\nConvert the document to markdown."

        sampling_params = SamplingParams(max_tokens=4096, temperature=0.1)

        # In production, you download r2_url to local bytes first
        # This is simplified vLLM usage:
        outputs = self.llm.generate(
            {"prompt": prompt_text, "multi_modal_data": {"image": r2_url}},
            sampling_params
        )
        return outputs[0].outputs[0].text

# Queue Consumer (HTTP Pull Emulation or Direct Call)
@app.function(schedule=modal.Period(seconds=5), secrets=[modal.Secret.from_name("parseflow-secrets")])
def poll_queue():
    import requests
    # 1. Pull from Cloudflare Queue via API
    # 2. Map to self.process.remote()
    # 3. Post back to WORKER_CALLBACK_URL with header x-internal-secret
    pass