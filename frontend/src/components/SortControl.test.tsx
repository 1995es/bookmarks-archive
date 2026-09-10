import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import SortControl from "./SortControl";

describe("SortControl", () => {
  it("reflects the current sort field and direction", () => {
    render(<SortControl sortBy="created_at" sortOrder="desc" onSortChange={vi.fn()} />);

    expect(screen.getByLabelText(/sort by/i)).toHaveValue("created_at:desc");
  });

  it("reports both field and direction when the selection changes", async () => {
    const onSortChange = vi.fn();
    const user = userEvent.setup();
    render(<SortControl sortBy="created_at" sortOrder="desc" onSortChange={onSortChange} />);

    await user.selectOptions(screen.getByLabelText(/sort by/i), "name:asc");

    expect(onSortChange).toHaveBeenCalledWith("name", "asc");
  });
});
