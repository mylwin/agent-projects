export interface Activity {
  id: string;
  time: string;
  title: string;
  description: string;
  location: string;
  kind: string;
  cost: number;
  point: number[] | null;
}

export interface TripDay {
  id: number;
  date: string;
  label: string;
  title: string;
  description: string;
  distance: string;
  activities: Activity[];
}

export interface Trip {
  schemaVersion: number;
  id: string;
  destination: string;
  travelers: number;
  budget: number;
  currency: string;
  days: TripDay[];
}

export interface Message {
  id: string;
  role: "assistant" | "user";
  content: string;
  time: string;
  revisionId?: string;
}

export interface PlanRevision {
  id: string;
  number: number;
  title: string;
  createdAt: string;
  trip: Trip;
}

export interface PlanProject {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  trip: Trip;
  messages: Message[];
  requests: { dayId: number; text: string }[];
  revisions: PlanRevision[];
  draft: boolean;
  finalRevisionId: string | null;
  pending: { text: string; dayId: number } | null;
}
