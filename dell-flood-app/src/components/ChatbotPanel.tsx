import React, { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Platform,
  Dimensions,
} from 'react-native';
import {
  Send,
  Bot,
  User,
  Sparkles,
  Search,
  ExternalLink,
  Layers,
  MapPin,
  Compass,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  FileText
} from 'lucide-react-native';
import { apiService, DetectionResult } from '../services/api';

interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  toolCalls?: Array<{
    tool_name: string;
    args: any;
    result_summary?: string;
  }>;
  citations?: string[];
  geocodedCoords?: [number, number];
  timestamp: string;
}

interface ChatbotPanelProps {
  lastResult?: DetectionResult | null;
  activeLocationName?: string;
  onNavigateToCoords?: (lat: number, lon: number, name?: string) => void;
  onOpenReportModal?: () => void;
}

const STARTER_PROMPTS = [
  { label: '🌊 Galveston Flood Risk', prompt: 'What is the flood risk around Galveston, Texas?' },
  { label: '🏔️ Aspen Terrain & Slope', prompt: 'Check terrain elevation and slope in Aspen, CO' },
  { label: '🔮 24h TWI Runoff Watch', prompt: 'Run a 24-hour predictive TWI runoff accumulation forecast for this active area' },
  { label: '🏃 Find High-Ground Shelters', prompt: 'Find the nearest elevation-safe evacuation shelters and road corridors nearby' },
];

export const ChatbotPanel: React.FC<ChatbotPanelProps> = ({
  lastResult,
  activeLocationName,
  onNavigateToCoords,
  onOpenReportModal,
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'init-1',
      sender: 'assistant',
      text: 'Hello! I am Project Aegis AI — powered by OpenAI GPT-4o with real-time MirEye Earth API geospatial intelligence.\n\nAsk me anything about real-time flood risk, terrain elevation, D8 runoff pooling, evacuation routes, or municipal disaster mitigation for any location in the US or globally.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({});

  const scrollViewRef = useRef<ScrollView>(null);

  useEffect(() => {
    scrollViewRef.current?.scrollToEnd({ animated: true });
  }, [messages, isLoading]);

  const toggleToolExpand = (id: string) => {
    setExpandedTools(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const handleSend = async (customText?: string) => {
    const textToSend = (customText || inputText).trim();
    if (!textToSend || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: textToSend,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages(prev => [...prev, userMsg]);
    if (!customText) setInputText('');
    setIsLoading(true);

    try {
      const locationContext = lastResult
        ? {
            location: activeLocationName || 'Active Scan Area',
            area_sq_km: lastResult.area_sq_km,
            severity: lastResult.severity,
            affected_population: lastResult.impact.population,
            damaged_buildings: lastResult.impact.buildings,
          }
        : activeLocationName
        ? { location: activeLocationName }
        : null;

      const conversationHistory = messages.slice(-8).map(m => ({
        role: m.sender === 'user' ? 'user' : 'assistant',
        content: m.text,
      }));

      const res = await apiService.sendChatMessage(textToSend, conversationHistory, locationContext);

      const botMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        sender: 'assistant',
        text: res.reply || res.response || 'Analysis complete.',
        toolCalls: res.tool_calls_executed || [],
        citations: res.citations || [],
        geocodedCoords: res.geocoded_coords || undefined,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };

      setMessages(prev => [...prev, botMsg]);
    } catch (err: any) {
      const errorMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        sender: 'assistant',
        text: `Error contacting Aegis Chatbot service: ${err.message || 'Network error'}. Please ensure the backend is running.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      {/* Header Banner */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.botBadge}>
            <Sparkles size={18} color="#2563eb" />
          </View>
          <View>
            <Text style={styles.headerTitle}>Aegis Intelligent Chatbot</Text>
            <Text style={styles.headerSubtitle}>OpenAI GPT-4o × MirEye Earth API</Text>
          </View>
        </View>
        {lastResult && onOpenReportModal && (
          <TouchableOpacity style={styles.reportHeaderBtn} onPress={onOpenReportModal}>
            <FileText size={14} color="#2563eb" />
            <Text style={styles.reportHeaderBtnText}>Bulletin PDF</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* Messages Scroll Area */}
      <ScrollView
        ref={scrollViewRef}
        style={styles.messageScroll}
        contentContainerStyle={styles.messageList}
        showsVerticalScrollIndicator={false}
      >
        {messages.map(msg => {
          const isUser = msg.sender === 'user';
          return (
            <View
              key={msg.id}
              style={[
                styles.messageRow,
                isUser ? styles.userRow : styles.botRow,
              ]}
            >
              {!isUser && (
                <View style={styles.avatarBot}>
                  <Bot size={16} color="#2563eb" />
                </View>
              )}

              <View style={[styles.bubble, isUser ? styles.userBubble : styles.botBubble]}>
                {/* Tool Calls Execution Pill */}
                {!isUser && msg.toolCalls && msg.toolCalls.length > 0 && (
                  <View style={styles.toolCallsContainer}>
                    {msg.toolCalls.map((tc, idx) => {
                      const toolKey = `${msg.id}-tool-${idx}`;
                      const isExpanded = !!expandedTools[toolKey];
                      return (
                        <View key={toolKey} style={styles.toolCard}>
                          <TouchableOpacity
                            style={styles.toolCardHeader}
                            onPress={() => toggleToolExpand(toolKey)}
                          >
                            <View style={styles.toolCardLeft}>
                              <Layers size={13} color="#2563eb" />
                              <Text style={styles.toolNameText}>
                                Tool: <Text style={styles.toolNameHighlight}>{tc.tool_name}</Text>
                              </Text>
                            </View>
                            {isExpanded ? (
                              <ChevronUp size={14} color="#64748b" />
                            ) : (
                              <ChevronDown size={14} color="#64748b" />
                            )}
                          </TouchableOpacity>
                          {isExpanded && (
                            <View style={styles.toolDetails}>
                              <Text style={styles.toolArgsText}>
                                Args: {JSON.stringify(tc.args, null, 2)}
                              </Text>
                              {tc.result_summary ? (
                                <Text style={styles.toolResultText}>
                                  Summary: {tc.result_summary}
                                </Text>
                              ) : null}
                            </View>
                          )}
                        </View>
                      );
                    })}
                  </View>
                )}

                {/* Message Text */}
                <Text style={[styles.messageText, isUser ? styles.userText : styles.botText]}>
                  {msg.text}
                </Text>

                {/* Geocoded Navigation Chip */}
                {!isUser && msg.geocodedCoords && onNavigateToCoords && (
                  <TouchableOpacity
                    style={styles.geoNavigateBtn}
                    onPress={() =>
                      onNavigateToCoords(
                        msg.geocodedCoords![0],
                        msg.geocodedCoords![1],
                        'Selected from Chat'
                      )
                    }
                  >
                    <MapPin size={14} color="#2563eb" />
                    <Text style={styles.geoNavigateText}>
                      View Location on Map ({msg.geocodedCoords[0].toFixed(3)}°, {msg.geocodedCoords[1].toFixed(3)}°)
                    </Text>
                  </TouchableOpacity>
                )}

                {/* Citation Badges */}
                {!isUser && msg.citations && msg.citations.length > 0 && (
                  <View style={styles.citationsContainer}>
                    <Text style={styles.citationsLabel}>Official Data Sources:</Text>
                    <View style={styles.citationChipsWrap}>
                      {msg.citations.map((c, i) => (
                        <View key={i} style={styles.citationChip}>
                          <CheckCircle2 size={11} color="#10b981" />
                          <Text style={styles.citationText}>{c}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}

                <Text style={[styles.timeText, isUser ? styles.userTimeText : styles.botTimeText]}>{msg.timestamp}</Text>
              </View>

              {isUser && (
                <View style={styles.avatarUser}>
                  <User size={16} color="#ffffff" />
                </View>
              )}
            </View>
          );
        })}

        {isLoading && (
          <View style={[styles.messageRow, styles.botRow]}>
            <View style={styles.avatarBot}>
              <Bot size={16} color="#2563eb" />
            </View>
            <View style={[styles.bubble, styles.botBubble, styles.loadingBubble]}>
              <ActivityIndicator size="small" color="#2563eb" />
              <Text style={styles.loadingText}>
                Querying MirEye Earth API & GPT-4o reasoning...
              </Text>
            </View>
          </View>
        )}
      </ScrollView>

      {/* Quick Starter Chips */}
      <View style={styles.starterContainer}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.starterScroll}>
          {STARTER_PROMPTS.map((sp, idx) => (
            <TouchableOpacity
              key={idx}
              style={styles.starterChip}
              onPress={() => handleSend(sp.prompt)}
              disabled={isLoading}
            >
              <Text style={styles.starterChipText}>{sp.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>

      {/* Input Bar */}
      <View style={styles.inputContainer}>
        <TextInput
          style={styles.textInput}
          placeholder="Ask about US flood risk, elevation, TWI runoff, shelters..."
          placeholderTextColor="#94a3b8"
          value={inputText}
          onChangeText={setInputText}
          multiline={false}
          onSubmitEditing={() => handleSend()}
          returnKeyType="send"
          editable={!isLoading}
        />
        <TouchableOpacity
          style={[styles.sendButton, (!inputText.trim() || isLoading) && styles.sendButtonDisabled]}
          onPress={() => handleSend()}
          disabled={!inputText.trim() || isLoading}
        >
          <Send size={18} color="#ffffff" />
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    backgroundColor: '#ffffff',
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0',
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 3,
    elevation: 2,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  botBadge: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#bfdbfe',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    color: '#0f172a',
    fontSize: 15,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#64748b',
    fontSize: 12,
    marginTop: 1,
  },
  reportHeaderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#bfdbfe',
  },
  reportHeaderBtnText: {
    color: '#2563eb',
    fontSize: 12,
    fontWeight: '600',
  },
  messageScroll: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  messageList: {
    paddingHorizontal: 16,
    paddingVertical: 16,
    gap: 16,
  },
  messageRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  botRow: {
    justifyContent: 'flex-start',
  },
  avatarBot: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#bfdbfe',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 2,
  },
  avatarUser: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#2563eb',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 2,
  },
  bubble: {
    maxWidth: '82%',
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  userBubble: {
    backgroundColor: '#2563eb',
    borderBottomRightRadius: 2,
    shadowColor: '#2563eb',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 2,
  },
  botBubble: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderBottomLeftRadius: 2,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 5,
    elevation: 1,
  },
  loadingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  loadingText: {
    color: '#64748b',
    fontSize: 13,
  },
  messageText: {
    fontSize: 14,
    lineHeight: 22,
  },
  userText: {
    color: '#ffffff',
  },
  botText: {
    color: '#0f172a',
  },
  toolCallsContainer: {
    marginBottom: 10,
    gap: 6,
  },
  toolCard: {
    backgroundColor: '#f8fafc',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    overflow: 'hidden',
  },
  toolCardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: '#f1f5f9',
  },
  toolCardLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  toolNameText: {
    color: '#64748b',
    fontSize: 11,
  },
  toolNameHighlight: {
    color: '#2563eb',
    fontWeight: '700',
  },
  toolDetails: {
    padding: 8,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  toolArgsText: {
    color: '#334155',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
  },
  toolResultText: {
    color: '#64748b',
    fontSize: 11,
    marginTop: 4,
  },
  geoNavigateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#eff6ff',
    borderWidth: 1,
    borderColor: '#bfdbfe',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginTop: 10,
    alignSelf: 'flex-start',
  },
  geoNavigateText: {
    color: '#2563eb',
    fontSize: 12,
    fontWeight: '600',
  },
  citationsContainer: {
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  citationsLabel: {
    color: '#64748b',
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 4,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  citationChipsWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  citationChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#f8fafc',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  citationText: {
    color: '#475569',
    fontSize: 11,
    fontWeight: '500',
  },
  timeText: {
    fontSize: 10,
    alignSelf: 'flex-end',
    marginTop: 4,
  },
  userTimeText: {
    color: 'rgba(255, 255, 255, 0.75)',
  },
  botTimeText: {
    color: '#94a3b8',
  },
  starterContainer: {
    paddingVertical: 8,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
  },
  starterScroll: {
    paddingHorizontal: 16,
    gap: 8,
  },
  starterChip: {
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
  },
  starterChipText: {
    color: '#334155',
    fontSize: 12,
    fontWeight: '500',
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    gap: 10,
  },
  textInput: {
    flex: 1,
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 10,
    color: '#0f172a',
    fontSize: 14,
  },
  sendButton: {
    width: 42,
    height: 42,
    borderRadius: 10,
    backgroundColor: '#2563eb',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#2563eb',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 2,
  },
  sendButtonDisabled: {
    backgroundColor: '#94a3b8',
    shadowOpacity: 0,
  },
});

