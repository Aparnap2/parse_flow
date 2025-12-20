import { Agent } from 'pydantic_ai';

async function testGraniteDocling() {
  console.log('Testing granite-docling LLM...');

  try {
    const agent = Agent(
      'ollama:granite-docling',
      {
        result_type: String,
        system_prompt: 'You are a document analysis assistant. Extract key information from the provided text.'
      },
      { base_url: 'http://localhost:11434/v1' }
    );

    const result = await agent.run('Extract vendor name from: Invoice from Acme Corp, total $123.45');
    console.log('Granite-docling result:', result.output);
    console.log('✅ Granite-docling test passed');

  } catch (error) {
    console.error('❌ Granite-docling test failed:', error);
    throw error;
  }
}

testGraniteDocling().catch(console.error);