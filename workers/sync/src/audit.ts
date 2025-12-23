export async function performAudit(data: any, db: any, userId: string, schema_json?: string): Promise<{ valid: boolean, flags: string[], score: number }> {
  const flags: string[] = [];
  let score = 1.0;

  // Schema and normalization checks
  if (schema_json) {
    try {
      const schema = JSON.parse(schema_json);
      // Check required fields based on schema
      if (schema.required) {
        for (const field of schema.required) {
          if (!data[field] || data[field] === null || data[field] === '') {
            flags.push(`Missing required field: ${field}`);
            score *= 0.8;
          }
        }
      }
    } catch (e) {
      console.error('Error parsing schema_json:', e);
    }
  }

  // Validation for flat invoice fields
  if (!data.vendor || typeof data.vendor !== 'string' || data.vendor.trim() === '') {
    flags.push('Missing or invalid vendor name');
    score *= 0.8;
  }

  if (!data.date || typeof data.date !== 'string') {
    flags.push('Missing or invalid date');
    score *= 0.8;
  } else {
    // Validate date format (YYYY-MM-DD)
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRegex.test(data.date)) {
      flags.push('Date format invalid, expected YYYY-MM-DD');
      score *= 0.8;
    } else {
      // Additional date validation - ensure it's a valid date
      const dateObj = new Date(data.date);
      if (isNaN(dateObj.getTime())) {
        flags.push('Date is not a valid calendar date');
        score *= 0.8;
      }
    }
  }

  if (data.total === undefined || data.total === null) {
    flags.push('Missing total amount');
    score *= 0.8;
  } else {
    // Convert to number if it's a string
    const total = typeof data.total === 'string' ? parseFloat(data.total) : data.total;
    if (isNaN(total) || total < 0) {
      flags.push('Total amount must be a positive number');
      score *= 0.8;
    } else {
      // Normalize total to number
      data.total = total;
    }
  }

  if (!data.invoice_number || typeof data.invoice_number !== 'string') {
    flags.push('Missing or invalid invoice number');
    score *= 0.8;
  }

  // Normalize date if needed
  if (typeof data.date === 'string' && data.date.includes('/')) {
    // Convert MM/DD/YYYY or MM/DD/YY to YYYY-MM-DD
    const dateParts = data.date.split('/');
    if (dateParts.length === 3) {
      let [month, day, year] = dateParts;
      if (year.length === 2) {
        year = '20' + year; // Assume 21st century for 2-digit years
      }
      data.date = `${year.padStart(4, '0')}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`;
    }
  }

  // Validation for line items
  if (data.line_items && Array.isArray(data.line_items)) {
    for (let i = 0; i < data.line_items.length; i++) {
      const item = data.line_items[i];
      if (typeof item.price !== 'number') {
        const price = typeof item.price === 'string' ? parseFloat(item.price.replace(/[^\d.-]/g, '')) : item.price;
        if (isNaN(price)) {
          flags.push(`Line item ${i} has invalid price`);
          score *= 0.9;
        } else {
          item.price = price;
        }
      }
      if (typeof item.quantity !== 'number') {
        const quantity = typeof item.quantity === 'string' ? parseFloat(item.quantity) : item.quantity;
        if (isNaN(quantity) || quantity < 0) {
          flags.push(`Line item ${i} has invalid quantity`);
          score *= 0.9;
        } else {
          item.quantity = quantity;
        }
      }
    }
  }

  // Math validation (after normalizing total)
  const total = typeof data.total === 'string' ? parseFloat(data.total) : data.total;
  if (data.line_items && Array.isArray(data.line_items)) {
    const lineTotal = data.line_items.reduce((sum: number, item: any) => {
      const price = typeof item.price === 'string' ? parseFloat(item.price.replace(/[^\d.-]/g, '')) : item.price;
      const quantity = typeof item.quantity === 'string' ? parseFloat(item.quantity) : item.quantity;
      return sum + (isNaN(price) ? 0 : price) * (isNaN(quantity) ? 0 : quantity);
    }, 0);

    if (Math.abs(lineTotal - total) > 0.05) {
      flags.push(`Math Error: Line items = $${lineTotal.toFixed(2)}, Total claims $${total}`);
      score *= 0.8;
    }
  }

  // Duplicate check
  const dup = await db.prepare(`
    SELECT id FROM historical_invoices
    WHERE user_id = ? AND vendor_name = ? AND invoice_number = ?
  `).bind(userId, data.vendor, data.invoice_number).first();

  if (dup) {
    flags.push("DUPLICATE: Invoice already processed");
    score *= 0.5;
  }

  // Price spike check (using normalized total)
  const avg = await db.prepare(`
    SELECT AVG(total_amount) as vendor_avg
    FROM historical_invoices WHERE user_id = ? AND vendor_name = ?
  `).bind(userId, data.vendor).first();

  if (avg && avg.vendor_avg && total > avg.vendor_avg * 1.5) {
    const pct = ((total/avg.vendor_avg-1)*100).toFixed(0);
    flags.push(`PRICE SPIKE: ${pct}% above avg`);
    score *= 0.7;
  }

  return { valid: flags.length === 0, flags, score };
}