import { take } from './queue';

export async function work(deliver: (item: unknown) => Promise<void>) {
  const item = take();
  if (item) await deliver(item);
}
