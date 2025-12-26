import requests
import base64
import json

def test_deepseek_ocr():
    # Read and encode the image
    with open('test_invoice.png', 'rb') as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Prepare the payload
    payload = {
        "model": "deepseek-ocr:3b",
        "prompt": "<image>\n<|grounding|>Convert the document to markdown.",
        "images": [encoded_image],
        "stream": False
    }
    
    # Send the request
    response = requests.post('http://localhost:11434/api/generate', json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print("DeepSeek OCR Response:")
        print(result.get('response', 'No response text'))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

def test_granite_docling():
    # Read and encode the image
    with open('test_invoice.png', 'rb') as image_file:
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')
    
    # Prepare the payload
    payload = {
        "model": "ibm/granite-docling:latest",
        "prompt": "Convert this document to markdown format preserving structure, tables, and text content. Focus on accuracy and layout preservation.",
        "images": [encoded_image],
        "stream": False
    }
    
    # Send the request
    response = requests.post('http://localhost:11434/api/generate', json=payload)
    
    if response.status_code == 200:
        result = response.json()
        print("\nGranite Docling Response:")
        print(result.get('response', 'No response text'))
    else:
        print(f"Error: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    print("Testing DeepSeek OCR model...")
    test_deepseek_ocr()
    
    print("\nTesting Granite Docling model...")
    test_granite_docling()