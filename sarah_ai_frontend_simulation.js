/**
 * Sarah AI Frontend Simulation
 * 
 * This file demonstrates the Sarah AI frontend components without modifying the existing ParseFlow UI
 */

// Blueprint Builder UI Simulation
function createBlueprintBuilder() {
  return `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Sarah AI - Blueprint Builder</title>
      <script src="https://cdn.tailwindcss.com"></script>
      <script src="https://unpkg.com/htmx.org"></script>
    </head>
    <body class="bg-gray-100">
      <div class="container mx-auto p-8">
        <h1 class="text-3xl font-bold mb-6">Create Extraction Blueprint</h1>
        <form id="blueprint-form" class="bg-white p-6 rounded-lg shadow">
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
        
        // Handle form submission
        document.getElementById('blueprint-form').addEventListener('submit', function(e) {
          e.preventDefault();
          
          // In a real implementation, this would send the data to the backend
          document.getElementById('response').innerHTML = 
            '<div class="bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded relative">Blueprint created successfully!</div>';
        });
      </script>
    </body>
    </html>
  `;
}

// HITL Dashboard UI Simulation
function createHitlDashboard() {
  return `
    <!DOCTYPE html>
    <html>
    <head>
      <title>Sarah AI - HITL Dashboard</title>
      <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-100">
      <div class="container mx-auto p-8">
        <h1 class="text-3xl font-bold mb-6">HITL Dashboard - Review Needed</h1>
        
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <!-- PDF Preview -->
          <div class="bg-white p-6 rounded-lg shadow">
            <h2 class="text-xl font-bold mb-4">Document Preview</h2>
            <div class="border-2 border-dashed border-gray-300 rounded-lg h-96 flex items-center justify-center">
              <p class="text-gray-500">PDF Preview would appear here</p>
            </div>
          </div>
          
          <!-- Data Review Form -->
          <div class="bg-white p-6 rounded-lg shadow">
            <h2 class="text-xl font-bold mb-4">Extracted Data</h2>
            <form id="review-form">
              <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2">Vendor</label>
                <input type="text" value="Home Depot" class="w-full border p-2 rounded" />
              </div>
              
              <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2">Total Amount</label>
                <input type="text" value="$1,024.99" class="w-full border p-2 rounded" />
              </div>
              
              <div class="mb-4">
                <label class="block text-gray-700 text-sm font-bold mb-2">Invoice Date</label>
                <input type="text" value="2025-12-20" class="w-full border p-2 rounded" />
              </div>
              
              <div class="mb-6">
                <label class="block text-gray-700 text-sm font-bold mb-2">Tax Amount</label>
                <input type="text" value="$82.00" class="w-full border p-2 rounded" />
              </div>
              
              <div class="flex gap-4">
                <button type="button" class="bg-green-600 hover:bg-green-700 text-white py-2 px-4 rounded">Approve</button>
                <button type="button" class="bg-yellow-500 hover:bg-yellow-600 text-white py-2 px-4 rounded">Request Changes</button>
                <button type="button" class="bg-gray-500 hover:bg-gray-600 text-white py-2 px-4 rounded">More Info</button>
              </div>
            </form>
          </div>
        </div>
        
        <!-- Spend Chart -->
        <div class="mt-8 bg-white p-6 rounded-lg shadow">
          <h2 class="text-xl font-bold mb-4">Spend Analysis</h2>
          <div class="border-2 border-dashed border-gray-300 rounded-lg h-64 flex items-center justify-center">
            <p class="text-gray-500">Chart visualization would appear here</p>
          </div>
        </div>
      </div>
    </body>
    </html>
  `;
}

// Google OAuth Simulation
function simulateGoogleAuth() {
  console.log("Simulating Google OAuth flow...");
  console.log("- Redirecting to Google for authentication");
  console.log("- User grants permission");
  console.log("- Receiving user profile data");
  console.log("- Creating/updating user in database");
  console.log("- Redirecting to dashboard");
}

// Lemon Squeezy Billing Simulation
function simulateLemonSqueezyBilling() {
  console.log("Simulating Lemon Squeezy billing flow...");
  console.log("- Creating checkout session");
  console.log("- Collecting payment information");
  console.log("- Creating subscription");
  console.log("- Setting up usage tracking");
  console.log("- Processing usage records");
}

// Rate Limiting Simulation
function simulateRateLimiting() {
  console.log("Simulating rate limiting for email processing...");
  console.log("- Checking IP against rate limit");
  console.log("- Allowing request if under limit");
  console.log("- Dropping request if over limit");
  console.log("- Preventing infinite loops");
}

// Error Handling Simulation
function simulateErrorHandling() {
  console.log("Simulating error handling for PDF processing...");
  console.log("- Catching PDF processing errors");
  console.log("- Sending 'Oops' email to sender");
  console.log("- Logging error for debugging");
  console.log("- Continuing with other emails");
}

// Main execution
console.log("=== Sarah AI Frontend Simulation ===");
console.log("This simulation demonstrates the frontend components of Sarah AI");
console.log("without modifying the existing ParseFlow implementation.\n");

console.log("1. Blueprint Builder UI:");
console.log("   Simulating the creation of custom extraction schemas");
console.log(createBlueprintBuilder().substring(0, 200) + "...");
console.log("");

console.log("2. HITL Dashboard UI:");
console.log("   Simulating the review interface for extracted data");
console.log(createHitlDashboard().substring(0, 200) + "...");
console.log("");

console.log("3. Google OAuth Flow:");
simulateGoogleAuth();
console.log("");

console.log("4. Lemon Squeezy Billing:");
simulateLemonSqueezyBilling();
console.log("");

console.log("5. Rate Limiting:");
simulateRateLimiting();
console.log("");

console.log("6. Error Handling:");
simulateErrorHandling();
console.log("");

console.log("=== Simulation Complete ===");