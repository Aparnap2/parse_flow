import { Agent } from 'pydantic_ai';

async function testMinistralLLM() {
  console.log('Testing ministral-3 LLM extraction...');

  try {
    const agent = Agent(
      'ollama:ministral-3',
      {
        result_type: {
          vendor_name: 'string',
          total_amount: 'number',
          invoice_date: 'string',
          currency: 'string',
          invoice_number: 'string'
        },
        system_prompt: 'Extract invoice data precisely. Return null if field is missing.'
      },
      { base_url: 'http://localhost:11434/v1' }
    );

    const testText = `
    INVOICE
    Vendor: Acme Corp
    Invoice #: INV-2023-001
    Date: 2023-12-15
    Total: $123.45 USD
    Thank you for your business!
    `;

    const result = await agent.run(`Extract from: ${testText}`);
    console.log('Ministral-3 extraction result:', result.output);

    // Validate
    const data = result.output;
    if (data.vendor_name === 'Acme Corp' && data.total_amount === 123.45) {
      console.log('✅ Ministral-3 extraction test passed');
    } else {
      console.log('❌ Ministral-3 extraction validation failed');
    }

  } catch (error) {
    console.error('❌ Ministral-3 test failed:', error);
    throw error;
  }
}

testMinistralLLM().catch(console.error);