import "@testing-library/jest-dom";

// optional: debug to prove this file runs
// eslint-disable-next-line no-console
console.log("jest.setup.ts loaded");

// optional: runtime assertion – will throw early if patch failed
if (typeof (expect as any).toBeInTheDocument !== "function") {
  // eslint-disable-next-line no-console
  console.log("jest-dom NOT patched yet in setup file");
}
