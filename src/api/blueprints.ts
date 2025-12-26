import { Hono } from 'hono';
import { drizzle } from 'drizzle-orm/d1';
import { zValidator } from '@hono/zod-validator';
import { z } from 'zod';
import { blueprints, users } from '../db/schema';

const app = new Hono();

// GET /blueprints/new - Blueprint Builder UI
app.get('/new', async (c) => {
  const userId = c.req.cookie('user_id');
  if (!userId) {
    return c.redirect('/');
  }

  return c.html(`
    <!DOCTYPE html>
    <html>
    <head>
      <title>Create Extraction Blueprint | Sarah AI</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <script src="https://unpkg.com/htmx.org"></script>
    </head>
    <body class="bg-gray-100">
      <div class="container mx-auto p-8">
        <h1 class="text-3xl font-bold mb-6">Create Extraction Blueprint</h1>
        <form hx-post="/blueprints" hx-target="#response" class="bg-white p-6 rounded-lg shadow">
          <div class="mb-4">
            <label class="block text-gray-700 text-sm font-bold mb-2" for="blueprint-name">
              Blueprint Name
            </label>
            <input 
              class="shadow appearance-none border rounded w-full py-2 px-3 text-gray-700 leading-tight focus:outline-none focus:shadow-outline" 
              id="blueprint-name" 
              type="text" 
              name="name" 
              placeholder="e.g., Xero Import">
          </div>
          
          <div id="fields-container">
            <div class="flex flex-col gap-2 mb-4 p-4 border rounded">
              <div class="grid grid-cols-12 gap-2">
                <div class="col-span-5">
                  <label class="block text-gray-700 text-sm font-bold mb-2">Column Name</label>
                  <input name="field_name[]" placeholder="Column Name (e.g. Total)" class="w-full border p-2 rounded" />
                </div>
                <div class="col-span-5">
                  <label class="block text-gray-700 text-sm font-bold mb-2">AI Instruction</label>
                  <input name="instruction[]" placeholder="AI Instruction (e.g. Include Tax)" class="w-full border p-2 rounded" />
                </div>
                <div class="col-span-2">
                  <label class="block text-gray-700 text-sm font-bold mb-2">Type</label>
                  <select name="type[]" class="w-full border p-2 rounded">
                    <option value="text">Text</option>
                    <option value="currency">Currency</option>
                    <option value="number">Number</option>
                    <option value="date">Date</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
          
          <button type="button" onclick="addField()" class="bg-gray-200 hover:bg-gray-300 text-gray-800 py-2 px-4 rounded mb-4">+ Add Column</button>
          <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline">Save Blueprint</button>
        </form>
        
        <div id="response" class="mt-4"></div>
      </div>
      
      <script>
        function addField() {
          const container = document.getElementById('fields-container');
          const newField = document.createElement('div');
          newField.className = 'flex flex-col gap-2 mb-4 p-4 border rounded';
          newField.innerHTML = `
            <div class="grid grid-cols-12 gap-2">
              <div class="col-span-5">
                <label class="block text-gray-700 text-sm font-bold mb-2">Column Name</label>
                <input name="field_name[]" placeholder="Column Name (e.g. Total)" class="w-full border p-2 rounded" />
              </div>
              <div class="col-span-5">
                <label class="block text-gray-700 text-sm font-bold mb-2">AI Instruction</label>
                <input name="instruction[]" placeholder="AI Instruction (e.g. Include Tax)" class="w-full border p-2 rounded" />
              </div>
              <div class="col-span-2">
                <label class="block text-gray-700 text-sm font-bold mb-2">Type</label>
                <select name="type[]" class="w-full border p-2 rounded">
                  <option value="text">Text</option>
                  <option value="currency">Currency</option>
                  <option value="number">Number</option>
                  <option value="date">Date</option>
                </select>
              </div>
            </div>
            <button type="button" onclick="removeField(this)" class="self-end bg-red-500 hover:bg-red-700 text-white py-1 px-2 rounded text-sm">Remove</button>
          `;
          container.appendChild(newField);
        }
        
        function removeField(button) {
          button.parentElement.remove();
        }
      </script>
    </body>
    </html>
  `);
});

// POST /blueprints - Create new blueprint
app.post('/', async (c) => {
  const userId = c.req.cookie('user_id');
  if (!userId) {
    return c.redirect('/');
  }

  const formData = await c.req.formData();
  const name = formData.get('name') as string;
  const fieldNames = formData.getAll('field_name[]') as string[];
  const instructions = formData.getAll('instruction[]') as string[];
  const types = formData.getAll('type[]') as string[];

  // Validate that we have matching arrays
  if (fieldNames.length !== instructions.length || fieldNames.length !== types.length) {
    return c.json({ error: 'Mismatched field data' }, 400);
  }

  // Create schema JSON
  const schema = fieldNames.map((name, index) => ({
    name: name,
    type: types[index],
    instruction: instructions[index]
  }));

  const db = drizzle(c.env.DB);
  
  try {
    const [newBlueprint] = await db.insert(blueprints).values({
      id: `bp_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      user_id: userId,
      name,
      schema_json: JSON.stringify(schema)
    }).returning();

    return c.html(`
      <div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative" role="alert">
        <strong class="font-bold">Success! </strong>
        <span class="block sm:inline">Blueprint "${newBlueprint.name}" created successfully.</span>
        <span class="absolute top-0 bottom-0 right-0 px-4 py-3">
          <a href="/blueprints/new" class="text-green-700 hover:text-green-900">Create another</a>
        </span>
      </div>
    `);
  } catch (error) {
    console.error('Error creating blueprint:', error);
    return c.html(`
      <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
        <strong class="font-bold">Error! </strong>
        <span class="block sm:inline">Failed to create blueprint: ${error.message}</span>
      </div>
    `);
  }
});

// GET /blueprints - List user's blueprints
app.get('/', async (c) => {
  const userId = c.req.cookie('user_id');
  if (!userId) {
    return c.redirect('/');
  }

  const db = drizzle(c.env.DB);
  
  try {
    const userBlueprints = await db.select().from(blueprints).where(
      db.schema.blueprints.user_id.eq(userId)
    ).all();

    const blueprintsList = userBlueprints.map(bp => `
      <div class="bg-white p-4 rounded-lg shadow mb-4">
        <h3 class="font-bold text-lg">${bp.name}</h3>
        <p class="text-gray-600 text-sm">ID: ${bp.id}</p>
        <div class="mt-2">
          <pre class="text-xs bg-gray-100 p-2 rounded">${bp.schema_json}</pre>
        </div>
      </div>
    `).join('');

    return c.html(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>My Blueprints | Sarah AI</title>
        <script src="https://cdn.tailwindcss.com"></script>
      </head>
      <body class="bg-gray-100">
        <div class="container mx-auto p-8">
          <h1 class="text-3xl font-bold mb-6">My Blueprints</h1>
          <a href="/blueprints/new" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded mb-6 inline-block">Create New Blueprint</a>
          <div>
            ${blueprintsList || '<p class="text-gray-600">No blueprints yet. <a href="/blueprints/new" class="text-blue-600">Create your first blueprint</a>.</p>'}
          </div>
        </div>
      </body>
      </html>
    `);
  } catch (error) {
    console.error('Error fetching blueprints:', error);
    return c.html(`
      <div class="container mx-auto p-8">
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded relative" role="alert">
          <strong class="font-bold">Error! </strong>
          <span class="block sm:inline">Failed to fetch blueprints: ${error.message}</span>
        </div>
      </div>
    `);
  }
});

export default app;