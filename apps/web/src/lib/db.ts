import { PrismaClient } from "@prisma/client/edge";
import { withAccelerate } from "@prisma/extension-accelerate";

const prisma = new PrismaClient().$extends(withAccelerate());

// Comment out the full RLS implementation for initial testing
// export const db = {
//   // Use this for user-facing queries (Enforces RLS)
//   async withRLS<T>(workspaceId: string, fn: (tx: any) => Promise<T>) {
//     return prisma.$transaction(async (tx) => {
//       // 1. Set the session variable for this transaction
//       await tx.$executeRawUnsafe(
//         `SELECT set_config('app.current_workspace_id', $1, true)`,
//         workspaceId
//       );
//       // 2. Run the user's query
//       return fn(tx);
//     });
//   },
//
//   // Use this for System/Worker actions only (Bypasses RLS logic if needed, or sets sudo)
//   async sudo<T>(fn: (tx: any) => Promise<T>) {
//       // For ingestion, we might not set RLS or set a 'system' context
//       return fn(prisma);
//   }
// };

// For testing purposes, export the raw prisma client
export const db = prisma;