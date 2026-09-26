/**
 * Every word the tour says, in one place.
 *
 * Edit freely: nothing here is logic. Steps are keyed by the ids in steps.ts,
 * and a test fails if a step has no copy or copy names a step that is gone.
 *
 * House style: second person, short, and specific to what is on screen. Say
 * what to do and what it shows. No "simply", no "powerful", no selling -- the
 * sample is there to be checked, not admired.
 */

import type { PathId } from "./types";

export interface StepCopy {
  title: string;
  body: string;
  /** Label for the assist button, when "Show me" is the wrong verb. */
  assist?: string;
}

export interface PathCopy {
  name: string;
  who: string;
  preview: {
    title: string;
    lede: string;
    /** What the finished result shows, one line each. Drawn as the result. */
    result: {
      heading: string;
      rows: Array<{ label: string; value: string }>;
      footnote: string;
    };
  };
  steps: Record<string, StepCopy>;
  finish: { title: string; body: string };
}

export const PATH_COPY: Record<PathId, PathCopy> = {
  lead: {
    name: "Lead",
    who: "You decide where expert hours go.",
    preview: {
      title: "Find where the model is sure and wrong, and package the fix",
      lede: "Six actions on sample data, about two minutes. This is what you'll have built:",
      result: {
        heading: "Package · Source selection (FAR 15.3)",
        rows: [
          { label: "Reasoning traces, model wrong", value: "3" },
          { label: "Left out: author not qualified", value: "1" },
          { label: "Left out: personal information", value: "1" },
        ],
        footnote: "Each record hashed, and the file hashed as a whole.",
      },
    },
    steps: {
      "open-map": {
        title: "Open the weakness map",
        body: "It shows where the model is wrong, by knowledge area.",
      },
      "raise-bar": {
        title: "Raise the bar to 0.9",
        body:
          "Set Confident at to ≥ 0.9 and watch which area keeps its count. " +
          "That's where the model is wrong and sure of it.",
      },
      "pick-area": {
        title: "Open Source selection",
        body:
          "8 of its 9 wrong answers came with 0.9 confidence or more, and 2 of those " +
          "problems have no expert answer yet.",
      },
      "open-problem": {
        title: "Open the top problem",
        body: "Problems the model failed that no qualified expert has solved come first.",
      },
      "see-answer": {
        title: "Read what the model said",
        body:
          "Open the model's answer. It was judged wrong 3 times, at 0.91 confidence or " +
          "more each time.",
      },
      "build-package": {
        title: "Package it for the lab",
        body:
          "In Packages, give it a name, pick Source selection, and build it. " +
          "The platform decides what may leave, not you.",
        assist: "Fill it in for me",
      },
    },
    finish: {
      title: "That's the loop",
      body:
        "You found where the model is confidently wrong and built a delivery for exactly " +
        "that. Three traces went in. Two were left out, and the manifest says why. No " +
        "score anywhere: the counts and the hash are the evidence.",
    },
  },

  expert: {
    name: "Expert",
    who: "You solve the problems.",
    preview: {
      title: "Solve one problem the model gets wrong",
      lede: "Six actions on sample data, about three minutes. This is what you'll have made:",
      result: {
        heading: "Trace recorded · counts as expert data",
        rows: [
          { label: "The model's answer", value: "wrong, 0.94 confident" },
          { label: "Yours", value: "in your own words" },
          { label: "Each step, with what it rests on", value: "FAR cited" },
        ],
        footnote: "Timed, marked UNCLASSIFIED, and hashed with SHA-256.",
      },
    },
    steps: {
      "open-solve": {
        title: "Open Solve",
        body: "This is where you work problems. The ones the model gets wrong come first.",
      },
      "pick-problem": {
        title: "Take the top problem",
        body:
          "The model got it wrong 3 times, sure of itself each time, and no qualified " +
          "expert has solved it yet.",
      },
      "read-material": {
        title: "Open the Section M excerpt",
        body:
          "The material you'd have on the job. Leave the model's answer closed for now: it " +
          "stays shut so it can't anchor you.",
      },
      "write-step": {
        title: "Write your first step",
        body: "Say what you checked and what it rests on, like FAR 15.306(d).",
        assist: "Use a worked example",
      },
      "record": {
        title: "Answer, then record it",
        body: "Write your answer below the steps and record the trace.",
        assist: "Fill it in and record",
      },
      "compare": {
        title: "Now open the model's answer",
        body: "You solved it blind. See what the model said, and how sure it was.",
      },
    },
    finish: {
      title: "That's the data a lab can't get elsewhere",
      body:
        "The model gave a contracting officer the wrong answer at 0.94 confidence. Your " +
        "reasoning is now recorded as expert data with its own SHA-256, ready to be " +
        "packaged for the lab.",
    },
  },
};

export const UI = {
  tourName: "Sample tour",
  stepOf: (n: number, total: number) => `Step ${n} of ${total}`,
  showMe: "Show me",
  exit: "Exit tour",
  next: "Next",
  close: "Close",

  preview: {
    label: "Take the tour",
    choose: "Which describes your work?",
    start: "Start",
    notNow: "Not now",
    sampleNote: "Runs on sample data. Nothing you do is saved, and your real data is untouched.",
  },

  banner: {
    text: "Sample data. Nothing you do here is saved or sent anywhere.",
    exit: "Exit sample",
  },

  dock: {
    paused: (n: number) => `Paused at step ${n}. You've left the page it's on.`,
    back: (n: number) => `Back to step ${n}`,
  },

  missing: "This step's control isn't on screen yet. Show me will take you to it.",

  resume: {
    text: (name: string, n: number, total: number) =>
      `Pick up the ${name} tour at step ${n} of ${total}?`,
    resume: "Resume",
    over: "Start over",
    dismiss: "Dismiss",
  },

  finish: {
    exit: "Back to my data",
    other: (name: string) => `Try the ${name} path`,
    replay: "Replay",
  },

  exited: "Tour closed. Replay it any time from the ? menu.",

  help: {
    button: "Help",
    gettingStarted: "Getting started",
    take: "Take the tour",
    replay: "Replay the tour",
    presenter: "Presenter mode",
  },

  presenter: {
    title: "Presenter",
    lede: "Jump to any step. The sample is reset for each jump.",
    preview: "Preview",
    reset: "Reset sample",
    close: "Close",
  },

  welcome: {
    title: "Getting started",
    subtitle:
      "Two short tours on sample data. Each ends with something finished that you did " +
      "yourself.",
    start: (name: string) => `Start the ${name} tour`,
    replay: (name: string) => `Replay the ${name} tour`,
    done: "Done",
    sample: "Nothing you do in a tour is saved, and your real data is never touched.",
  },
};
