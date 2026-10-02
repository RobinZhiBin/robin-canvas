const pending: {reference: string}[] = [];

export const enqueue = (payload: {reference: string}) => {
  pending.push(payload);
  return {accepted: true};
};

export function take() {
  return pending.shift();
}
