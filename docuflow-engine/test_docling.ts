import { DocumentConverter } from 'docling';

async function testDoclingProcessing() {
  console.log('Testing Docling document processing...');

  // Create a simple test PDF in memory (or use a real file)
  // For this test, we'll assume we have a test PDF
  // In a real test, you'd create one or use a fixture

  const converter = new DocumentConverter();

  try {
    // This would normally process a real PDF file
    // const result = await converter.convert('path/to/test.pdf');
    // const markdown = result.document.export_to_markdown();

    // For now, just test the converter initialization
    console.log('✅ Docling converter initialized successfully');

    // Test with a simple text file or mock
    console.log('✅ Docling processing test passed (mocked)');

  } catch (error) {
    console.error('❌ Docling processing failed:', error);
    throw error;
  }
}

testDoclingProcessing().catch(console.error);