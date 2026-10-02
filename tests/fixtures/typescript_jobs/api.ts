import { enqueue } from './queue';

export function submit(payload: {reference: string}) {
  if (!payload.reference) throw new Error('reference required');
  return enqueue(payload);
}
