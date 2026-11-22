// API Types

export interface User {
  id: number;
  phone_number: string;
  name: string;
}

export interface LoginRequest {
  phone_number: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Document {
  id: number;
  original_name: string;
  file_size: number;
  upload_date: string;
  is_processed: boolean;
}

export interface Agent {
  id: number;
  name: string;
  ai_model: string;
  created_at: string;
  document_count: number;
}


// Customer support types

export type Intent =
  | 'faq' | 'order_status' | 'return_request' | 'cancel_order' | 'product_info'
  | 'talk_to_human' | 'complaint' | 'greeting' | 'other';

export interface SupportChatResponse {
  session_id: number;
  answer: string;
  intent: Intent;
  intent_confidence: number;
  classifier: 'llm' | 'baseline';
  entities: Record<string, string>;
  sentiment_label: 'positive' | 'neutral' | 'negative';
  sentiment_score: number;
  escalated: boolean;
  ticket_id: number | null;
  response_time_ms: number;
}

export interface OrderItemSummary {
  product: string;
  quantity: number;
  unit_price: number;
}

export interface OrderSummary {
  order_number: string;
  status: 'placed' | 'shipped' | 'out_for_delivery' | 'delivered' | 'cancelled';
  placed_on: string | null;
  shipped_on: string | null;
  delivered_on: string | null;
  expected_delivery: string | null;
  carrier: string | null;
  tracking_number: string | null;
  total: number;
  items: OrderItemSummary[];
}

export interface SupportTicket {
  id: number;
  customer: string;
  customer_phone: string;
  session_id: number | null;
  channel: 'text' | 'voice';
  reason: string;
  priority: 'urgent' | 'high' | 'normal' | 'low';
  sentiment_score: number | null;
  summary: string | null;
  status: 'open' | 'assigned' | 'resolved';
  created_at: string;
}

export interface FeedbackRequest {
  session_id: number | null;
  channel: 'text' | 'voice';
  rating: number;
  resolved: boolean | null;
  comment?: string;
}

export interface LiveKitTokenResponse {
  server_url: string;
  token: string;
  room: string;
  session_id: number;
}

export interface LatencyStats {
  count: number;
  mean_ms: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
}

export interface SatisfactionStats {
  count: number;
  average_rating: number | null;
  resolved_pct: number | null;
  distribution: Record<string, number>;
}

export interface ClassifierScore {
  accuracy: number;
  macro_f1: number;
  test_size: number;
}

export interface SupportMetrics {
  intent_accuracy: { llm?: ClassifierScore; baseline?: ClassifierScore; llm_full_dataset?: ClassifierScore; evaluated_at?: string } | null;
  appropriateness: { reviewed_turns: number; scores: Record<string, number>; overall: number } | null;
  response_time: Record<'text' | 'voice' | 'all', LatencyStats>;
  satisfaction: Record<'text' | 'voice' | 'all', SatisfactionStats>;
  volume: { sessions: number; sessions_by_channel: Record<string, number>; user_turns: number };
  intent_distribution: Record<string, number>;
  classifier_usage: Record<string, number>;
  sentiment_distribution: Record<string, number>;
  average_sentiment: number | null;
  escalation: {
    escalated_sessions: number;
    rate_pct: number | null;
    open_tickets: number;
    tickets_by_priority: Record<string, number>;
  };
}
