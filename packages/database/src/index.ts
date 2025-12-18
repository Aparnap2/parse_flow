import { PrismaClient } from "@prisma/client/edge";
import { withAccelerate } from "@prisma/extension-accelerate";

// For Prisma 7+, use accelerateUrl in the constructor
const prisma = new PrismaClient({
  // In production, this would be set from environment variable
  // accelerateUrl: process.env.DATABASE_URL
}).$extends(withAccelerate());

export const db = {
  // Enforces RLS via Session Variable
  async withRLS<T>(workspaceId: string, fn: (tx: any) => Promise<T>) {
    return prisma.$transaction(async (tx) => {
      await tx.$executeRawUnsafe(
        `SELECT set_config('app.current_workspace_id', $1, true)`,
        workspaceId
      );
      return fn(tx);
    });
  },
  // Bypasses RLS (Use with caution for system tasks)
  async sudo<T>(fn: (tx: any) => Promise<T>) {
      return fn(prisma);
  },
  // Get the PrismaClient instance for adapters (e.g., Better Auth)
  getClient: () => prisma
};

// Also export the raw client for advanced usage
export { prisma };