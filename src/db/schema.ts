import { sqliteTable, text, integer, real } from 'drizzle-orm/sqlite-core';
import { relations } from 'drizzle-orm';

export const users = sqliteTable('users', {
  id: text('id').primaryKey(),
  email: text('email').notNull().unique(),
  google_id: text('google_id').unique(), // For OAuth
  inbox_alias: text('inbox_alias').unique(), // 'uuid@sarah.ai'
  created_at: integer('created_at', { mode: 'timestamp' })
});

export const blueprints = sqliteTable('blueprints', {
  id: text('id').primaryKey(),
  user_id: text('user_id').references(() => users.id),
  name: text('name'), // "Xero Import"
  schema_json: text('schema_json'), // JSON: [{ name: "Total", type: "currency", instruction: "..." }]
  target_sheet_id: text('target_sheet_id') // Optional: Google Sheet ID
});

export const jobs = sqliteTable('jobs', {
  id: text('id').primaryKey(),
  user_id: text('user_id'),
  status: text('status'), // 'queued', 'review', 'completed'
  r2_key: text('r2_key'),
  result_json: text('result_json'), // Extracted Data
  confidence: real('confidence'),
  created_at: integer('created_at', { mode: 'timestamp' }),
  completed_at: integer('completed_at', { mode: 'timestamp' })
});

// Define relations
export const usersRelations = relations(users, ({ many }) => ({
  blueprints: many(blueprints),
  jobs: many(jobs)
}));

export const blueprintsRelations = relations(blueprints, ({ one }) => ({
  user: one(users, {
    fields: [blueprints.user_id],
    references: [users.id]
  })
}));

export const jobsRelations = relations(jobs, ({ one }) => ({
  user: one(users, {
    fields: [jobs.user_id],
    references: [users.id]
  })
}));