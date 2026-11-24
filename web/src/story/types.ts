import type { Bundle } from "../data";

/** What the story draws in: its section, the stage that holds still and the steps over it. */
export interface Context {
  bundle: Bundle;
  story: HTMLElement;
  stage: HTMLElement;
  steps: HTMLElement;
  reducedMotion: boolean;
  lite: boolean;
}
