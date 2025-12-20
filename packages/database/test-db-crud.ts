import { db } from './src/index';

async function testDBCRUD() {
  console.log('Testing DB CRUD operations...');

  // Create
  const doc = await db.sudo(tx => tx.document.create({
    data: {
      userId: 'test-user-id',
      r2Key: 'test-key.pdf',
      originalName: 'test.pdf',
      status: 'PENDING'
    }
  }));
  console.log('Created document:', doc.id);

  // Read
  const readDoc = await db.sudo(tx => tx.document.findUnique({
    where: { id: doc.id }
  }));
  console.log('Read document:', readDoc?.status);

  // Update
  const updatedDoc = await db.sudo(tx => tx.document.update({
    where: { id: doc.id },
    data: { status: 'COMPLETED', vendor: 'Test Vendor' }
  }));
  console.log('Updated document:', updatedDoc.vendor);

  // Delete
  await db.sudo(tx => tx.document.delete({
    where: { id: doc.id }
  }));
  console.log('Deleted document');

  console.log('✅ DB CRUD tests passed');
}

testDBCRUD().catch(console.error);