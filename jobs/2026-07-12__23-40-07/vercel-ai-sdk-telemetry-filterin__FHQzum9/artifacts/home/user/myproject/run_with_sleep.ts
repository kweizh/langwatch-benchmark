/* eslint-disable @typescript-eslint/no-explicit-any */
import { main } from "./run";

main().then(() => {
  // Give fetch a moment to complete
  return new Promise(r => setTimeout(r, 1500));
}).catch((e) => {
  console.error(e);
  process.exit(1);
});
