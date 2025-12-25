import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

export const createS3Client = (env: any) => new S3Client({
  region: 'auto',
  endpoint: `https://${env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: env.R2_ACCESS_KEY_ID,     // Set via wrangler secret
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  },
});

export const generatePresignedPut = async (env: any, key: string, contentType: string) => {
  const client = createS3Client(env);
  const cmd = new PutObjectCommand({
    Bucket: 'parseflow-storage', // Your bucket name
    Key: key,
    ContentType: contentType
  });
  return getSignedUrl(client, cmd, { expiresIn: 900 }); // 15 mins
};

export const generatePresignedGet = async (env: any, key: string) => {
  // Implementation for generating presigned GET URLs if needed
  // This would be similar to the PUT version but with GetObjectCommand
};