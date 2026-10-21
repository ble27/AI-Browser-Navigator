import { render, screen } from "@testing-library/react";
import { App } from "./App";

describe("App", () => {
  it("renders the shell", () => {
    render(<App />);
    expect(screen.getByTestId("app")).toBeInTheDocument();
  });
});
