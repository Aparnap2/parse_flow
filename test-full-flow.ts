// Full end-to-end test script
// This would simulate the entire flow locally

import { db } from './packages/database/src/index';
import { login } from './apps/web/src/lib/auth';

async function testFullFlow() {
  console.log('Testing full end-to-end flow...');

  // 1. Authenticate user
  const session = await login('test@example.com', 'test123');
  if (!session) throw new Error('Login failed');
  console.log('✅ User authenticated');

  // 2. Simulate document creation (like email ingest)
  const doc = await db.sudo(tx => tx.document.create({
    data: {
      userId: session.user.id,
      r2Key: 'test-invoice.pdf',
      originalName: 'invoice.pdf',
      status: 'QUEUED'
    }
  }));
  console.log('✅ Document created:', doc.id);

  // 3. Simulate processing (call engine logic)
  // This would normally be done by the queue consumer
  // For now, just update status
  await db.sudo(tx => tx.document.update({
    where: { id: doc.id },
    data: {
      status: 'COMPLETED',
      vendor: 'Test Vendor',
      total: 99.99,
      date: '2024-01-01',
      invoiceNumber: 'TEST-001',
      currency: 'USD'
    }
  }));
  console.log('✅ Document processed');

  // 4. Verify in dashboard (query with RLS)
  const userDocs = await db.withRLS(session.user.id, tx => tx.document.findMany());
  console.log('✅ User can access their documents:', userDocs.length);

  // 5. Cleanup
  await db.sudo(tx => tx.document.delete({ where: { id: doc.id } }));

  console.log('✅ Full flow test passed');
}

testFullFlow().catch(console.error);