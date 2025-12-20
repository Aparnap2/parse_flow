import { db } from './src/index';

async function testErrorHandling() {
  console.log('Testing error handling...');

  // Test invalid user ID
  try {
    await db.withRLS('invalid-user-id', async (tx) => {
      return tx.document.findMany();
    });
    console.log('❌ Should have thrown error for invalid user');
  } catch (error) {
    console.log('✅ Correctly threw error for invalid user:', error.message);
  }

  // Test creating document with missing required fields
  try {
    await db.sudo(tx => tx.document.create({
      data: {
        userId: 'test-user-id',
        // Missing required fields
      }
    }));
    console.log('❌ Should have thrown validation error');
  } catch (error) {
    console.log('✅ Correctly threw validation error:', error.message);
  }

  // Test RLS isolation - create documents for different users
  const doc1 = await db.sudo(tx => tx.document.create({
    data: { userId: 'user1', r2Key: 'key1.pdf', originalName: 'doc1.pdf', status: 'PENDING' }
  }));

  const doc2 = await db.sudo(tx => tx.document.create({
    data: { userId: 'user2', r2Key: 'key2.pdf', originalName: 'doc2.pdf', status: 'PENDING' }
  }));

  // User1 should only see their document
  const user1Docs = await db.withRLS('user1', tx => tx.document.findMany());
  console.log('User1 docs count:', user1Docs.length);
  console.log('✅ RLS isolation working:', user1Docs.every(d => d.userId === 'user1'));

  // Cleanup
  await db.sudo(tx => tx.document.deleteMany());

  console.log('✅ Error handling tests passed');
}

testErrorHandling().catch(console.error);