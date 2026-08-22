import React, { useState, useEffect, useRef } from 'react';
import { StyleSheet, View, Text, StatusBar, SafeAreaView, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, Alert, Dimensions, Platform, Linking } from 'react-native';
import { Map, AlertOctagon, Cpu, Settings as SettingsIcon, Shield, Users, LogOut, Lock, User, Plus, Filter, CheckSquare, MessageSquare, PhoneCall, Bell, Mail, Compass, Eye, ShieldAlert, Check, PlusCircle, FileText, Home, Activity } from 'lucide-react-native';
import * as Speech from 'expo-speech';
import * as Notifications from 'expo-notifications';
import { MapView } from './src/components/MapView';
import { ReportForm } from './src/components/ReportForm';
import { AgentPanel } from './src/components/AgentPanel';
import { SettingsPanel } from './src/components/SettingsPanel';
import { apiService, DEFAULT_API_URL, DetectionResult, CrowdReport, ShelterInfo } from './src/services/api';

type TabType = 'map' | 'report' | 'raise' | 'agent' | 'settings';
type UserRole = 'none' | 'citizen' | 'official';
type ScreenMode = 'login' | 'signup';

const { width } = Dimensions.get('window');

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export default function App() {
  const [role, setRole] = useState<UserRole>('none');
  const [screenMode, setScreenMode] = useState<ScreenMode>('login');
  const [activeTab, setActiveTab] = useState<TabType>('report');
  
  // Track seen complaint IDs to prevent notification loops
  const seenComplaintIdsRef = useRef<Set<number>>(new Set());
  const isInitialDashboardFetchRef = useRef<boolean>(true);
  
  // Auth Form State
  const [username, setUsername] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [phone, setPhone] = useState<string>('');
  const [authRole, setAuthRole] = useState<string>('citizen');
  const [loadingAuth, setLoadingAuth] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<string>('');
  const [authError, setAuthError] = useState<string>('');
  const [serverUrl, setServerUrl] = useState<string>(DEFAULT_API_URL);
  const [showServerConfig, setShowServerConfig] = useState<boolean>(false);

  // App Global states
  const [lastResult, setLastResult] = useState<DetectionResult | null>(null);
  const [activeLat, setActiveLat] = useState<number>(20.5937);
  const [activeLon, setActiveLon] = useState<number>(78.9629);
  
  // Dashboard complaints & stats states
  const [complaints, setComplaints] = useState<CrowdReport[]>([]);
  const [stats, setStats] = useState<any>({ total_active: 0, total_resolved: 0, location_groups: {} });
  const [loadingDashboard, setLoadingDashboard] = useState<boolean>(false);

  // Filters for Official Panel
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  const sevRank = (s: string) => {
    const up = (s || '').toUpperCase();
    if (up === 'CRITICAL' || up === 'SEVERE') return 4;
    if (up === 'HIGH') return 3;
    if (up === 'MODERATE' || up === 'MEDIUM') return 2;
    if (up === 'LOW' || up === 'MINOR') return 1;
    return 0;
  };

  const filteredComplaints = React.useMemo(() => {
    return complaints
      .filter(c => {
        const statusMatch = statusFilter === 'all' || c.status === statusFilter;
        const severityMatch = severityFilter === 'all' || c.severity === severityFilter;
        return statusMatch && severityMatch;
      })
      .sort((a, b) => {
        const diff = sevRank(b.severity) - sevRank(a.severity);
        if (diff !== 0) return diff;
        return (b.timestamp || 0) - (a.timestamp || 0);
      });
  }, [complaints, statusFilter, severityFilter]);

  // Shared Chatbot states
  const [chatQuery, setChatQuery] = useState<string>('');
  const [chatHistory, setChatHistory] = useState<{ q: string; a: string }[]>([]);
  const [chatLoading, setChatLoading] = useState<boolean>(false);

  // Live Toast & Push Token states
  const [notification, setNotification] = useState<{ title: string; message: string; type: 'emergency' | 'warning' | 'info' } | null>(null);
  const [pushToken, setPushToken] = useState<string>('');
  
  // Recipient email address input state (defaulted for demo convenience)
  const [recipientEmail, setRecipientEmail] = useState<string>('shahzeb03794@gmail.com');

  const [expandedComplaintId, setExpandedComplaintId] = useState<number | null>(null);

  // Assam report preview states
  const [assamHotspots, setAssamHotspots] = useState<any[]>([]);
  const [loadingAssamPreview, setLoadingAssamPreview] = useState<boolean>(false);
  const [showAssamPreview, setShowAssamPreview] = useState<boolean>(false);

  const handlePreviewAssamReport = async () => {
    if (showAssamPreview) {
      setShowAssamPreview(false);
      return;
    }
    
    if (assamHotspots.length > 0) {
      setShowAssamPreview(true);
      return;
    }

    setLoadingAssamPreview(true);
    try {
      const res = await apiService.getAssamTop10Preview();
      if (res.status === 'SUCCESS') {
        setAssamHotspots(res.hotspots);
        setShowAssamPreview(true);
      } else {
        Alert.alert('Error', 'Failed to retrieve state flood preview.');
      }
    } catch (e) {
      Alert.alert('Error', 'Assam report preview request failed.');
    } finally {
      setLoadingAssamPreview(false);
    }
  };

  useEffect(() => {
    // Initialize API Service (load custom API URL/mock state from storage)
    apiService.init().catch(err => console.log('API Service initialization failed:', err));

    // Restore session on page refresh
    try {
      if (Platform.OS === 'web') {
        const savedUser = localStorage.getItem('user_username');
        const savedRole = localStorage.getItem('user_role');
        if (savedUser && savedRole) {
          setCurrentUser(savedUser);
          setRole(savedRole as any);
          setActiveTab('report');
        }
      }
    } catch (e) {}

    registerForPushNotificationsAsync().then(token => {
      if (token) setPushToken(token);
    });
  }, []);

  useEffect(() => {
    if (role !== 'none') {
      fetchDashboardData(true);
    }
  }, [role, activeTab]);

  async function registerForPushNotificationsAsync() {
    if (Platform.OS === 'web') return '';
    try {
      if (Platform.OS === 'android') {
        await Notifications.setNotificationChannelAsync('default', {
          name: 'default',
          importance: Notifications.AndroidImportance.MAX,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: '#2563eb',
        }).catch(err => console.log('Notification channel setup error:', err));
      }
      const { status: existingStatus } = await Notifications.getPermissionsAsync().catch(() => ({ status: 'denied' }));
      let finalStatus = existingStatus;
      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync().catch(() => ({ status: 'denied' }));
        finalStatus = status;
      }
      if (finalStatus !== 'granted') {
        return '';
      }
      const token = (await Notifications.getExpoPushTokenAsync().catch(() => ({ data: '' }))).data;
      console.log('Expo Push Token Registered:', token);
      return token || '';
    } catch (e) {
      console.log('Error obtaining expo push token:', e);
      return '';
    }
  }

  const speakAlert = (text: string) => {
    // Voice assistant removed
  };

  const triggerNotification = (title: string, message: string, type: 'emergency' | 'warning' | 'info') => {
    try {
      setNotification({ title, message, type });
      speakAlert(`${title}. ${message}`);
      
      if (Platform.OS !== 'web') {
        Notifications.scheduleNotificationAsync({
          content: {
            title: `🚨 ${title.toUpperCase()}`,
            body: message,
            sound: true,
          },
          trigger: null,
        }).catch(err => console.log('[Notification schedule err]:', err));
      }

      // Trigger backend SMTP email alert to the configured recipient email
      if (recipientEmail && recipientEmail.includes('@')) {
        apiService.triggerEmailAlert(recipientEmail, title, message)
          .then(res => console.log('[SMTP Email Alert] Dispatched successfully:', res))
          .catch(err => console.log('[SMTP Email Alert] Dispatch failed:', err));
      }
      
      setTimeout(() => setNotification(null), 6000);
    } catch (err) {
      console.log('[triggerNotification caught error]:', err);
    }
  };

  const fetchDashboardData = async (isInitial = false) => {
    if (isInitial && complaints.length === 0) {
      setLoadingDashboard(true);
    }
    try {
      const data = await apiService.getComplaintsAndShelters();
      const currentList: CrowdReport[] = data.complaints || [];
      
      if (isInitialDashboardFetchRef.current) {
        // Seed seen IDs on first load so pre-existing complaints don't trigger notification storm
        currentList.forEach(c => {
          if (c.id) seenComplaintIdsRef.current.add(c.id);
        });
        isInitialDashboardFetchRef.current = false;
      } else if (role === 'official') {
        // Only alert if a genuinely new high-severity complaint arrived during this live session
        const unseenSevere = currentList.filter(
          c => c.id && !seenComplaintIdsRef.current.has(c.id) && (c.severity === 'SEVERE' || c.severity === 'CRITICAL')
        );
        
        if (unseenSevere.length > 0) {
          const newest = unseenSevere[0];
          triggerNotification(
            "New Critical Report",
            `Severe incident reported at ${newest.location_name || `${newest.lat.toFixed(2)}°N, ${newest.lon.toFixed(2)}°E`}`,
            "emergency"
          );
        }
        
        currentList.forEach(c => {
          if (c.id) seenComplaintIdsRef.current.add(c.id);
        });
      }
      
      setComplaints(currentList);
      if (data.stats) {
        setStats(data.stats);
      }
    } catch (e) {
      console.log("Error fetching complaints: ", e);
    } finally {
      if (isInitial) {
        setLoadingDashboard(false);
      }
    }
  };

  const handleLocationSelected = (result: DetectionResult, lat: number, lon: number) => {
    setLastResult(result);
    setActiveLat(lat);
    setActiveLon(lon);
    
    // Only alert on meaningful, confirmed high/critical flood inundation (never for normal dry ground)
    if (result.area_sq_km >= 0.5 && (result.severity === 'CRITICAL' || result.severity === 'HIGH')) {
      triggerNotification(
        `Active ${result.classification} Confirmed`,
        `Severity rated as ${result.severity} over an area of ${result.area_sq_km.toFixed(2)} sq km.`,
        "emergency"
      );
    }
  };

  const handleLogout = () => {
    seenComplaintIdsRef.current.clear();
    isInitialDashboardFetchRef.current = true;
    setRole('none');
    setUsername('');
    setPassword('');
    setPhone('');
    setCurrentUser('');
    setActiveTab('report');
    setChatHistory([]);
    setNotification(null);
    try {
      if (Platform.OS === 'web') {
        localStorage.removeItem('user_username');
        localStorage.removeItem('user_role');
      }
    } catch(e) {}
  };

  const handleAuthSubmit = async () => {
    setAuthError('');
    if (!username.trim() || !password.trim()) {
      setAuthError('Please complete all form fields.');
      return;
    }
    setLoadingAuth(true);
    try {
      if (screenMode === 'signup') {
        const res = await apiService.register(username, password, authRole, phone, pushToken);
        if (res.status === 'SUCCESS') {
          Alert.alert('Account Created', 'Please login with your new account.');
          setScreenMode('login');
          setUsername('');
          setPassword('');
          setPhone('');
        } else {
          setAuthError(res.detail || 'Registration failed.');
        }
      } else {
        const res = await apiService.login(username, password, pushToken);
        if (res.status === 'SUCCESS') {
          setCurrentUser(res.username);
          setRole(res.role);
          setActiveTab('report');
          setUsername('');
          setPassword('');
          setPhone('');
          setAuthError('');
          try {
            if (Platform.OS === 'web') {
              localStorage.setItem('user_username', res.username);
              localStorage.setItem('user_role', res.role);
            }
          } catch(e) {}
        } else {
          setAuthError('Invalid credentials.');
        }
      }
    } catch (e: any) {
      setAuthError(e.message || 'Credentials not found / Wrong password.');
    } finally {
      setLoadingAuth(false);
    }
  };

  const handleResolveComplaint = async (id: number) => {
    try {
      // Optimistic update in place to preserve scroll position
      setComplaints(prev => prev.map(c => c.id === id ? { ...c, status: 'resolved' } : c));
      setStats((prev: any) => ({
        ...prev,
        total_active: Math.max(0, (prev.total_active || 1) - 1),
        total_resolved: (prev.total_resolved || 0) + 1
      }));
      setExpandedComplaintId(null);
      const res = await apiService.resolveComplaint(id);
      if (res.status === 'SUCCESS') {
        triggerNotification("Report Resolved", "Ground report status marked resolved in SQL.", "info");
      }
    } catch (e) {
      Alert.alert('Error', 'Unable to update status.');
    }
  };

  const handleVoiceCallTrigger = async (phoneNum: string, severity: string) => {
    const alertMessage = `Emergency Alert: Active ${severity} water levels verified near your location. Route paths are updated. Please evacuate to the nearest safe shelter immediately.`;
    try {
      const res = await apiService.triggerVoiceCall(phoneNum, alertMessage);
      if (res.status === 'SUCCESS') {
        setExpandedComplaintId(null);
        triggerNotification("Twilio Voice Call Outbound", `Automated warning call dialed to ${phoneNum}.`, "info");
      }
    } catch (e) {
      Alert.alert('Error', 'Voice gateway request failed.');
    }
  };

  const handleEmailReportTrigger = async (c: CrowdReport) => {
    triggerNotification("Compiling RAG Report", "Invoking Gemini RAG compiler for situation brief...", "info");
    try {
      const seed = Math.abs(c.lat + c.lon);
      const isSevere = c.severity === 'SEVERE' || c.severity === 'HIGH' || c.severity === 'CRITICAL';
      const area = Math.round((isSevere ? 2.0 + (seed % 3) * 1.2 : 0.5 + (seed % 3) * 0.4) * 100) / 100;
      const pop = Math.round(area * 1150);
      const bld = Math.round(area * 40);
      const fac = area > 0 ? Math.max(1, Math.round(area * 0.4)) : 0;

      const locName = c.location_name || `${c.lat.toFixed(2)}°N, ${c.lon.toFixed(2)}°E District`;
      const payload = {
        to_email: recipientEmail,
        location: locName,
        lat: c.lat,
        lon: c.lon,
        area_sq_km: area,
        classification: "Flood Inundation",
        severity: c.severity,
        population_affected: pop,
        buildings_damaged: bld,
        facilities_at_risk: fac
      };
      
      const res = await apiService.triggerEmailReport(payload);
      if (res.status === 'SUCCESS') {
        setExpandedComplaintId(null);
        triggerNotification("Email Alert Sent", `LLM Situation brief sent to: ${recipientEmail}`, "info");
        Alert.alert('RAG Email Dispatched', `The following LLM report was sent successfully:\n\n${res.report}`);
      }
    } catch (e) {
      Alert.alert('Error', 'Direct SMTP dispatch request failed.');
    }
  };

  const handleBroadcastNotification = async (c: CrowdReport) => {
    triggerNotification("Broadcasting Push Alerts", "Publishing emergency push notifications to all users...", "info");
    try {
      const location = c.location_name || `${c.lat.toFixed(2)}°N, ${c.lon.toFixed(2)}°E District`;
      const seed = Math.abs(c.lat + c.lon);
      const isSevere = c.severity === 'SEVERE' || c.severity === 'HIGH' || c.severity === 'CRITICAL';
      const area = Math.round((isSevere ? 2.0 + (seed % 3) * 1.2 : 0.5 + (seed % 3) * 0.4) * 100) / 100;
      
      const res = await apiService.broadcastNotification(location, c.severity, area);
      if (res.status === 'SUCCESS') {
        setExpandedComplaintId(null);
        triggerNotification("Push Alert Broadcasted", res.message, "info");
        Alert.alert('Broadcast Dispatched', `Title: ${res.title}\nBody: ${res.body}\n\n${res.message}`);
      } else {
        Alert.alert('Broadcast Failed', res.message || 'Error occurred.');
      }
    } catch (e) {
      Alert.alert('Error', 'Push broadcast request failed.');
    }
  };

  const handleDeploySDRF = (location: string) => {
    setExpandedComplaintId(null);
    triggerNotification(
      "SDRF Dispatched", 
      `Rescue rafts and medical assets sent to coordinates near: ${location}`, 
      "emergency"
    );
  };

  const renderRegionalImpactReport = () => {
    if (!lastResult) {
      return (
        <View style={styles.panelCard}>
          <View style={styles.cardHeader}>
            <FileText size={18} color="#64748b" />
            <Text style={styles.cardTitle}>Active Regional Disaster Brief</Text>
          </View>
          <Text style={styles.noDataText}>💡 Select a village or run satellite inference on the map to generate the spatial impact report.</Text>
        </View>
      );
    }

    const popPerc = Math.min(100, (lastResult.impact.population / 15000) * 100);
    const bldPerc = Math.min(100, (lastResult.impact.buildings / 500) * 100);

    return (
      <View style={styles.panelCard}>
        <View style={styles.cardHeader}>
          <FileText size={18} color="#ef4444" />
          <Text style={styles.cardTitle}>📑 Active Disaster Impact Brief (Full Report)</Text>
        </View>
        <View style={styles.reportBulletin}>
          <Text style={styles.reportSummaryTitle}>
            📍 Target Area: {lastResult.classification} ({lastResult.severity} RISK)
          </Text>
          <Text style={styles.reportSummaryMeta}>
            Coordinates: {activeLat.toFixed(4)}° N, {activeLon.toFixed(4)}° E • Confidence: {lastResult.confidence_score}%
          </Text>

          <View style={styles.reportDivider} />

          {/* Section 1: Human Population Impact */}
          <View style={styles.reportSectionRow}>
            <View style={styles.reportSectionIconBg}>
              <Users size={16} color="#d97706" />
            </View>
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={styles.reportSectionLabel}>👥 Human Population Impact</Text>
              <Text style={styles.reportSectionValue}>{lastResult.impact.population.toLocaleString()} residents affected</Text>
              <View style={styles.reportProgressBarBg}>
                <View style={[styles.reportProgressBar, { width: `${popPerc}%`, backgroundColor: '#f59e0b' }]} />
              </View>
            </View>
          </View>

          {/* Section 2: Residential Structures */}
          <View style={styles.reportSectionRow}>
            <View style={styles.reportSectionIconBg}>
              <Home size={16} color="#dc2626" />
            </View>
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={styles.reportSectionLabel}>🏠 Residential Structures Compromised</Text>
              <Text style={styles.reportSectionValue}>{lastResult.impact.buildings} homes damaged</Text>
              <View style={styles.reportProgressBarBg}>
                <View style={[styles.reportProgressBar, { width: `${bldPerc}%`, backgroundColor: '#ef4444' }]} />
              </View>
            </View>
          </View>

          {/* Section 3: Critical Facilities */}
          <View style={styles.reportSectionRow}>
            <View style={styles.reportSectionIconBg}>
              <Activity size={16} color="#059669" />
            </View>
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={styles.reportSectionLabel}>🏫 Critical Facilities & Lifelines</Text>
              <View style={styles.infraStatusRow}>
                <Text style={styles.infraStatusDot}>🏥 Sadar Hospital: {lastResult.area_sq_km > 0 ? '🛑 FLOODED' : '🟢 SAFE'}</Text>
                <Text style={styles.infraStatusDot}>🏫 Government School: {lastResult.area_sq_km > 0 ? '🛑 INUNDATED' : '🟢 SAFE'}</Text>
                <Text style={styles.infraStatusDot}>🔌 Grid Powerlines: {lastResult.area_sq_km > 0 ? '🛑 DISCONNECTED' : '🟢 ACTIVE'}</Text>
              </View>
            </View>
          </View>

          {/* Recommendations block */}
          <View style={styles.recommendationsBlock}>
            <Text style={styles.recommendationsTitle}>💡 Recommended Actions:</Text>
            <Text style={styles.recommendationsText}>
              {lastResult.severity === 'CRITICAL' || lastResult.severity === 'HIGH'
                ? "Immediate emergency alerts have been triggered. Mobilize rescue boats, dispatch warnings via Twilio/SMS channels, and route affected residents to the nearest green shelter."
                : "Continuous satellite radar monitoring is active. No immediate evacuation is ordered, but municipal drain clearings are advised."}
            </Text>
          </View>
        </View>
      </View>
    );
  };

  const handleChatQuery = async () => {
    if (!chatQuery.trim()) return;
    setChatLoading(true);
    const userQ = chatQuery;
    setChatQuery('');
    try {
      const answer = await apiService.askQuestion(userQ, lastResult || undefined);
      setChatHistory(prev => [...prev, { q: userQ, a: answer }]);
    } catch (e) {
      setChatHistory(prev => [...prev, { q: userQ, a: "RAG service offline. Please try again later." }]);
    } finally {
      setChatLoading(false);
    }
  };

  const toggleScreenMode = () => {
    setScreenMode(screenMode === 'login' ? 'signup' : 'login');
    setUsername('');
    setPassword('');
    setPhone('');
    setAuthError('');
  };

  if (role === 'none') {
    return (
      <SafeAreaView style={styles.loginContainer}>
        <StatusBar barStyle="dark-content" backgroundColor="#f8fafc" />
        <View style={styles.logoHeader}>
          <Text style={styles.logoTitle}>AEGIS</Text>
          <Text style={styles.logoSubtitle}>Flood Detection & Response System</Text>
        </View>

        <View style={styles.authCard}>
          <Text style={styles.authTitle}>
            {screenMode === 'login' ? 'Sign In to Portal' : 'Register New Account'}
          </Text>

          {authError ? (
            <View style={styles.authErrorBox}>
              <Text style={styles.authErrorText}>⚠️ {authError}</Text>
            </View>
          ) : null}

          <View style={styles.inputWrapper}>
            <User size={16} color="#64748b" style={{ marginRight: 8 }} />
            <TextInput
              style={styles.authInput}
              placeholder="Username"
              placeholderTextColor="#94a3b8"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
            />
          </View>

          <View style={styles.inputWrapper}>
            <Lock size={16} color="#64748b" style={{ marginRight: 8 }} />
            <TextInput
              style={styles.authInput}
              placeholder="Password"
              placeholderTextColor="#94a3b8"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
              autoCapitalize="none"
            />
          </View>

          {screenMode === 'signup' && (
            <>
              <View style={styles.inputWrapper}>
                <TextInput
                  style={styles.authInput}
                  placeholder="Phone Number"
                  placeholderTextColor="#94a3b8"
                  keyboardType="phone-pad"
                  value={phone}
                  onChangeText={setPhone}
                />
              </View>

              <Text style={styles.authLabel}>Profile Access Role</Text>
              <View style={styles.roleChoiceRow}>
                <TouchableOpacity 
                  style={[styles.roleSelectBtn, authRole === 'citizen' && { backgroundColor: '#10b981', borderColor: '#10b981' }]}
                  onPress={() => setAuthRole('citizen')}
                >
                  <Text style={[styles.roleSelectBtnText, authRole === 'citizen' && { color: '#ffffff' }]}>Public Citizen</Text>
                </TouchableOpacity>

                <TouchableOpacity 
                  style={[styles.roleSelectBtn, authRole === 'official' && { backgroundColor: '#2563eb', borderColor: '#2563eb' }]}
                  onPress={() => setAuthRole('official')}
                >
                  <Text style={[styles.roleSelectBtnText, authRole === 'official' && { color: '#ffffff' }]}>Gov Official</Text>
                </TouchableOpacity>
              </View>
            </>
          )}

          <TouchableOpacity style={styles.authSubmitBtn} onPress={handleAuthSubmit} disabled={loadingAuth}>
            {loadingAuth ? (
              <ActivityIndicator size="small" color="#ffffff" />
            ) : (
              <Text style={styles.authSubmitBtnText}>
                {screenMode === 'login' ? 'Log In' : 'Create Account'}
              </Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity 
            style={styles.authToggleBtn} 
            onPress={toggleScreenMode}
          >
            <Text style={styles.authToggleBtnText}>
              {screenMode === 'login' ? "Don't have an account? Sign Up" : "Already have an account? Sign In"}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity 
            style={{ marginTop: 16, alignItems: 'center', paddingVertical: 4 }} 
            onPress={() => setShowServerConfig(!showServerConfig)}
          >
            <Text style={{ color: '#64748b', fontSize: 11 }}>⚙️ {showServerConfig ? "Hide Server Settings" : "Server Connection Settings"}</Text>
          </TouchableOpacity>

          {showServerConfig && (
            <View style={{ marginTop: 8, padding: 10, backgroundColor: '#f1f5f9', borderRadius: 8, borderWidth: 1, borderColor: '#e2e8f0' }}>
              <Text style={{ fontSize: 10, color: '#475569', fontWeight: 'bold', marginBottom: 4 }}>Backend API URL:</Text>
              <TextInput
                style={{ backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#cbd5e1', borderRadius: 6, paddingHorizontal: 8, height: 34, fontSize: 11, color: '#0f172a' }}
                value={serverUrl}
                onChangeText={(text) => {
                  setServerUrl(text);
                  apiService.setApiUrl(text);
                }}
                autoCapitalize="none"
                placeholder="http://10.142.212.139:8000/api"
              />
            </View>
          )}
        </View>
      </SafeAreaView>
    );
  }

  const renderChatbot = () => (
    <View style={styles.chatbotContainer}>
      <View style={styles.chatbotHeader}>
        <MessageSquare size={18} color="#2563eb" />
        <Text style={styles.chatbotTitle}>Flood Rescuer AI RAG Chatbot</Text>
      </View>
      {chatHistory.length > 0 && (
        <View style={styles.chatHistoryScroll}>
          {chatHistory.map((item, idx) => (
            <View key={`chat-${idx}`} style={styles.chatBubbleGroup}>
              <View style={styles.userBubble}>
                <Text style={styles.userBubbleText}>{item.q}</Text>
              </View>
              <View style={styles.botBubble}>
                <Text style={styles.botBubbleText}>{item.a}</Text>
              </View>
            </View>
          ))}
        </View>
      )}
      <View style={styles.chatInputRow}>
        <TextInput
          style={styles.chatInput}
          placeholder="Ask about safety measures (e.g. 'what should I do?')..."
          placeholderTextColor="#94a3b8"
          value={chatQuery}
          onChangeText={setChatQuery}
          onSubmitEditing={handleChatQuery}
        />
        <TouchableOpacity style={styles.chatSendBtn} onPress={handleChatQuery} disabled={chatLoading}>
          {chatLoading ? <ActivityIndicator size="small" color="#ffffff" /> : <Text style={styles.chatSendText}>Ask</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.safeContainer}>
      <StatusBar barStyle="dark-content" backgroundColor="#ffffff" />
      
      {/* Slide-Down glassmorphic banner */}
      {notification && (
        <View style={[
          styles.notificationToast,
          { 
            borderColor: notification.type === 'emergency' ? '#ef4444' : notification.type === 'warning' ? '#f59e0b' : '#2563eb',
            backgroundColor: notification.type === 'emergency' ? '#fef2f2' : '#f8fafc'
          }
        ]}>
          <Bell size={18} color={notification.type === 'emergency' ? '#ef4444' : '#2563eb'} style={{ marginRight: 10 }} />
          <View style={{ flex: 1 }}>
            <Text style={[styles.toastTitle, { color: '#0f172a' }]}>{notification.title}</Text>
            <Text style={[styles.toastMessage, { color: '#475569' }]}>{notification.message}</Text>
          </View>
        </View>
      )}

      {/* Header */}
      <View style={styles.appHeader}>
        <View style={styles.headerTitleCol}>
          <Text style={styles.headerTitle}>AEGIS</Text>
          <Text style={styles.headerSubtitle}>
            {role === 'citizen' ? `Citizen Dashboard (${currentUser})` : `Command Center (${currentUser})`}
          </Text>
        </View>
        <View style={styles.headerRightCol}>
          <View style={[styles.badge, { borderColor: role === 'citizen' ? '#10b981' : '#2563eb' }]}>
            <Text style={[styles.badgeText, { color: role === 'citizen' ? '#10b981' : '#2563eb' }]}>
              {role.toUpperCase()}
            </Text>
          </View>
          <TouchableOpacity style={styles.logoutBtn} onPress={handleLogout}>
            <LogOut size={16} color="#64748b" />
          </TouchableOpacity>
        </View>
      </View>

      <View style={styles.contentBody}>
        {activeTab === 'map' && (
          <MapView
            lastDetection={lastResult}
            onLocationSelected={handleLocationSelected}
            initialLat={activeLat}
            initialLon={activeLon}
          />
        )}

        {/* Dedicated Page to Raise Ground Issues ONLY */}
        {activeTab === 'raise' && (
          <ReportForm username={currentUser} onReported={fetchDashboardData} />
        )}

        {activeTab === 'report' && (
          role === 'citizen' ? (
            <ScrollView 
              style={styles.dashboardContainer} 
              contentContainerStyle={{ paddingBottom: 60 }}
              keyboardShouldPersistTaps="handled"
              removeClippedSubviews={false}
              showsVerticalScrollIndicator={true}
            >
              {/* Quick Navigation Hub Grid */}
              <View style={styles.hubGrid}>
                <TouchableOpacity style={styles.hubCard} onPress={() => setActiveTab('map')}>
                  <View style={[styles.hubIconBg, { backgroundColor: '#e0f2fe' }]}>
                    <Map size={20} color="#0284c7" />
                  </View>
                  <View style={styles.hubTextCol}>
                    <Text style={styles.hubCardTitle}>Interactive Map</Text>
                    <Text style={styles.hubCardDesc}>Explore satellite water segmentations & safe shelter coordinates.</Text>
                  </View>
                </TouchableOpacity>

                <TouchableOpacity style={styles.hubCard} onPress={() => setActiveTab('raise')}>
                  <View style={[styles.hubIconBg, { backgroundColor: '#fef2f2' }]}>
                    <PlusCircle size={20} color="#ef4444" />
                  </View>
                  <View style={styles.hubTextCol}>
                    <Text style={styles.hubCardTitle}>Raise Ground Issue</Text>
                    <Text style={styles.hubCardDesc}>Submit a new localized flood or rescue issue alert.</Text>
                  </View>
                </TouchableOpacity>
              </View>

              {renderRegionalImpactReport()}

              {renderChatbot()}

              <View style={styles.panelCard}>
                <View style={styles.cardHeader}>
                  <AlertOctagon size={18} color="#ef4444" />
                  <Text style={styles.cardTitle}>Personal Alert Warning Logs</Text>
                </View>
                {lastResult && (lastResult.severity === 'CRITICAL' || lastResult.severity === 'HIGH') ? (
                  <View style={styles.alertItem}>
                    <Text style={styles.alertItemTime}>Active Alert</Text>
                    <Text style={styles.alertItemText}>
                      {lastResult.severity}: Elevated flood risk verified near {activeLat.toFixed(2)}°N, {activeLon.toFixed(2)}°E. Evacuation paths and shelters are active on the interactive map.
                    </Text>
                  </View>
                ) : (
                  <Text style={styles.noDataText}>No critical emergency warnings in your immediate zone.</Text>
                )}
              </View>

              <View style={styles.panelCard}>
                <View style={styles.cardHeader}>
                  <CheckSquare size={18} color="#2563eb" />
                  <Text style={styles.cardTitle}>Personal Ground Warning Log</Text>
                </View>
                {loadingDashboard ? (
                  <ActivityIndicator size="small" color="#2563eb" />
                ) : complaints.filter(c => c.username === currentUser).length === 0 ? (
                  <Text style={styles.noDataText}>You have not submitted any reports yet.</Text>
                ) : (
                  complaints.filter(c => c.username === currentUser).map((c, index) => (
                    <View key={index} style={styles.logRow}>
                      <View style={styles.logRowLeft}>
                        <Text style={styles.logLocation}>{c.lat.toFixed(4)}N, {c.lon.toFixed(4)}E</Text>
                        <Text style={styles.logDesc}>{c.description}</Text>
                      </View>
                      <View style={styles.logRowRight}>
                        <View style={[styles.statusTag, { backgroundColor: c.status === 'resolved' ? '#d1fae5' : '#f3e8ff' }]}>
                          <Text style={[styles.statusText, { color: c.status === 'resolved' ? '#065f46' : '#6b21a8' }]}>
                            {c.status === 'resolved' ? 'RESOLVED' : 'UNDER REVIEW'}
                          </Text>
                        </View>
                        <Text style={styles.logModelStatus}>
                          {c.model_confirmed === 1 ? '✓ AI CONFIRMED' : '⏱ PENDING AI SCAN'}
                        </Text>
                      </View>
                    </View>
                  ))
                )}
              </View>

              <View style={styles.panelCard}>
                <View style={styles.cardHeader}>
                  <Users size={18} color="#2563eb" />
                  <Text style={styles.cardTitle}>Active Community Reports Feed</Text>
                </View>
                {loadingDashboard && complaints.length === 0 ? (
                  <ActivityIndicator size="small" color="#2563eb" />
                ) : complaints.filter(c => c.status !== 'resolved').length === 0 ? (
                  <Text style={styles.noDataText}>No active community alerts at this time.</Text>
                ) : (
                  complaints.filter(c => c.status !== 'resolved').slice(0, 5).map((c, index) => (
                    <View key={c.id ? `feed-${c.id}` : `feed-${index}`} style={styles.logRow}>
                      <View style={styles.logRowLeft}>
                        <Text style={styles.logLocation}>{c.lat.toFixed(4)}N, {c.lon.toFixed(4)}E • Severity: {c.severity}</Text>
                        <Text style={styles.logDesc}>{c.description}</Text>
                      </View>
                      <View style={styles.logRowRight}>
                        <View style={[styles.statusTag, { backgroundColor: '#f3e8ff' }]}>
                          <Text style={[styles.statusText, { color: '#6b21a8' }]}>ACTIVE</Text>
                        </View>
                      </View>
                    </View>
                  ))
                )}
              </View>
            </ScrollView>
          ) : (
            <ScrollView 
              style={styles.dashboardContainer} 
              contentContainerStyle={{ paddingBottom: 60 }}
              keyboardShouldPersistTaps="handled"
              removeClippedSubviews={false}
              showsVerticalScrollIndicator={true}
            >
              {/* Quick Navigation Hub Grid */}
              <View style={styles.hubGrid}>
                <TouchableOpacity style={styles.hubCard} onPress={() => setActiveTab('map')}>
                  <View style={[styles.hubIconBg, { backgroundColor: '#e0f2fe' }]}>
                    <Map size={20} color="#0284c7" />
                  </View>
                  <View style={styles.hubTextCol}>
                    <Text style={styles.hubCardTitle}>Interactive Map</Text>
                    <Text style={styles.hubCardDesc}>Run satellite models, preview radar bands, and inspect coordinates.</Text>
                  </View>
                </TouchableOpacity>

                <TouchableOpacity style={styles.hubCard} onPress={() => setActiveTab('agent')}>
                  <View style={[styles.hubIconBg, { backgroundColor: '#d1fae5' }]}>
                    <Cpu size={20} color="#065f46" />
                  </View>
                  <View style={styles.hubTextCol}>
                    <Text style={styles.hubCardTitle}>AI Agent Panel</Text>
                    <Text style={styles.hubCardDesc}>Trigger autonomous monitoring cycle checks and view decision trace logs.</Text>
                  </View>
                </TouchableOpacity>
              </View>

              {renderRegionalImpactReport()}

              {renderChatbot()}
              
              <TouchableOpacity 
                style={styles.testAlertBtn} 
                onPress={() => triggerNotification("Emergency Test Notification", "This is an automated Text-To-Speech alert check.", "emergency")}
              >
                <Bell size={14} color="#ffffff" style={{ marginRight: 6 }} />
                <Text style={styles.testAlertText}>Trigger Live Test Warning Notification</Text>
              </TouchableOpacity>

              {/* Assam State Flood Report Card (White Theme) */}
              <View style={styles.panelCard}>
                <View style={styles.cardHeader}>
                  <FileText size={18} color="#2563eb" style={{ marginRight: 6 }} />
                  <Text style={styles.cardTitle}>Assam Flood Severity Report</Text>
                </View>
                <Text style={styles.helperText}>
                  Preview current regional critical priorities or export as a multi-page PDF document for offline rescue coordination:
                </Text>

                <View style={{ flexDirection: 'row', gap: 10, marginTop: 10 }}>
                  <TouchableOpacity 
                    style={{ flex: 1, backgroundColor: '#2563eb', paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 8 }} 
                    onPress={handlePreviewAssamReport}
                    disabled={loadingAssamPreview}
                  >
                    {loadingAssamPreview ? (
                      <ActivityIndicator size="small" color="#ffffff" />
                    ) : (
                      <>
                        <Eye size={14} color="#ffffff" style={{ marginRight: 6 }} />
                        <Text style={{ color: '#ffffff', fontWeight: 'bold', fontSize: 12 }}>
                          {showAssamPreview ? "Hide Preview" : "Preview Report"}
                        </Text>
                      </>
                    )}
                  </TouchableOpacity>

                  <TouchableOpacity 
                    style={{ flex: 1, backgroundColor: '#10b981', paddingVertical: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', borderRadius: 8 }} 
                    onPress={() => {
                      const reportUrl = `${DEFAULT_API_URL}/reports/assam-top10`;
                      Linking.openURL(reportUrl)
                        .catch(err => Alert.alert('Error', 'Unable to open download URL.'));
                    }}
                  >
                    <Compass size={14} color="#ffffff" style={{ marginRight: 6 }} />
                    <Text style={{ color: '#ffffff', fontWeight: 'bold', fontSize: 12 }}>Download PDF</Text>
                  </TouchableOpacity>
                </View>

                {showAssamPreview && assamHotspots.length > 0 && (
                  <View style={{ marginTop: 12, backgroundColor: '#f8fafc', borderRadius: 8, padding: 8, borderWidth: 1, borderColor: '#e2e8f0' }}>
                    <Text style={{ fontSize: 11, fontWeight: 'bold', color: '#0f172a', marginBottom: 6 }}>
                      State Mitigation Priority (Sorted by Severity):
                    </Text>
                    {assamHotspots.map((hs, idx) => (
                      <View key={idx} style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5, borderBottomWidth: idx === assamHotspots.length - 1 ? 0 : 0.5, borderBottomColor: '#cbd5e1' }}>
                        <Text style={{ fontSize: 11, color: '#334155', fontWeight: '600' }}>
                          {idx + 1}. {hs.name}
                        </Text>
                        <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
                          <View style={{ backgroundColor: hs.severity === 'CRITICAL' ? '#fef2f2' : hs.severity === 'HIGH' ? '#fffbeb' : '#f0fdf4', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 }}>
                            <Text style={{ fontSize: 9, fontWeight: 'bold', color: hs.severity === 'CRITICAL' ? '#dc2626' : hs.severity === 'HIGH' ? '#b45309' : '#15803d' }}>
                              {hs.severity}
                            </Text>
                          </View>
                          <Text style={{ fontSize: 10, color: '#64748b', minWidth: 60, textAlign: 'right' }}>
                            {hs.area}
                          </Text>
                        </View>
                      </View>
                    ))}
                  </View>
                )}
              </View>

              {/* Recipient Email configuration card */}
              <View style={styles.panelCard}>
                <View style={styles.cardHeader}>
                  <Mail size={18} color="#2563eb" />
                  <Text style={styles.cardTitle}>Demo Recipient Email Configuration</Text>
                </View>
                <Text style={styles.helperText}>Enter the email address where the LLM generated situation bulletins should be sent:</Text>
                <TextInput
                  style={styles.emailConfigInput}
                  value={recipientEmail}
                  onChangeText={setRecipientEmail}
                  placeholder="e.g. disaster-center@bihar.gov.in"
                  placeholderTextColor="#94a3b8"
                  autoCapitalize="none"
                />
              </View>

              <View style={styles.statsCardRow}>
                <View style={styles.statBox}>
                  <Text style={styles.statNumber}>{stats.total_active}</Text>
                  <Text style={styles.statLabel}>Active Warnings</Text>
                </View>
                <View style={styles.statBox}>
                  <Text style={[styles.statNumber, { color: '#10b981' }]}>{stats.total_resolved}</Text>
                  <Text style={styles.statLabel}>Resolved Warnings</Text>
                </View>
              </View>

              <View style={styles.panelCard}>
                <View style={styles.cardHeader}>
                  <Filter size={18} color="#2563eb" />
                  <Text style={styles.cardTitle}>Complaints Grouped By District Location</Text>
                </View>
                {Object.keys(stats.location_groups).length === 0 ? (
                  <Text style={styles.noDataText}>No active locations.</Text>
                ) : (
                  Object.entries(stats.location_groups).map(([loc, count], idx) => (
                    <View key={idx} style={styles.groupRow}>
                      <Text style={styles.groupLocName}>{loc}</Text>
                      <View style={styles.groupCountBadge}>
                        <Text style={styles.groupCountText}>{(count as number)} reports</Text>
                      </View>
                    </View>
                  ))
                )}
              </View>

              <View style={styles.filterCard}>
                <View style={styles.filterHeader}>
                  <Filter size={14} color="#64748b" />
                  <Text style={styles.filterTitle}>Queue Filtering Filters</Text>
                </View>
                <View style={styles.filterOptionRow}>
                  <Text style={styles.filterLabelSmall}>Status: </Text>
                  {['all', 'pending', 'resolved'].map(st => (
                    <TouchableOpacity 
                      key={st} 
                      style={[styles.filterBtn, statusFilter === st && styles.filterBtnActive]}
                      onPress={() => setStatusFilter(st)}
                    >
                      <Text style={[styles.filterBtnText, statusFilter === st && styles.filterBtnTextActive]}>{st.toUpperCase()}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View style={styles.panelCard}>
                <View style={[styles.cardHeader, { justifyContent: 'space-between' }]}>
                  <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                    <AlertOctagon size={18} color="#f97316" />
                    <Text style={styles.cardTitle}>Ranked Incident Queue</Text>
                  </View>
                  <TouchableOpacity 
                    style={{ backgroundColor: '#eff6ff', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, borderWidth: 1, borderColor: '#bfdbfe' }}
                    onPress={() => fetchDashboardData(true)}
                  >
                    <Text style={{ color: '#1e40af', fontSize: 10, fontWeight: 'bold' }}>🔄 Refresh</Text>
                  </TouchableOpacity>
                </View>
                {loadingDashboard && complaints.length === 0 ? (
                  <ActivityIndicator size="small" color="#2563eb" />
                ) : filteredComplaints.length === 0 ? (
                  <Text style={styles.noDataText}>No warnings match active filters.</Text>
                ) : (
                  filteredComplaints.map((c, index) => {
                    const matchPercent = c.score 
                      ? Math.round(c.score) 
                      : (c.severity === 'SEVERE' || c.severity === 'CRITICAL' ? 96 : c.severity === 'HIGH' ? 86 : c.severity === 'MODERATE' ? 78 : 55);
                    const formattedTime = c.timestamp 
                      ? `${new Date(c.timestamp * 1000).toLocaleDateString([], { month: 'short', day: 'numeric' })}, ${new Date(c.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` 
                      : 'Just now';
                    const displayPlace = c.location_name ? c.location_name : `${c.lat.toFixed(4)}°N, ${c.lon.toFixed(4)}°E`;

                    return (
                      <View key={c.id ? `ranked-${c.id}` : `ranked-${index}`} style={styles.rankedRow}>
                        <View style={styles.rankedRowTop}>
                          <View style={[styles.rankedBadge, { backgroundColor: c.severity === 'SEVERE' || c.severity === 'CRITICAL' ? '#fef2f2' : '#f0fdf4' }]}>
                            <Text style={[styles.rankedBadgeText, { color: c.severity === 'SEVERE' || c.severity === 'CRITICAL' ? '#dc2626' : '#16a34a' }]}>
                              {matchPercent}% Match
                            </Text>
                          </View>
                          <Text style={styles.rankedLocText} numberOfLines={1}>
                            📍 {displayPlace}
                          </Text>
                          <Text style={[styles.rankedSevText, { color: c.severity === 'SEVERE' || c.severity === 'CRITICAL' ? '#ef4444' : c.severity === 'HIGH' ? '#f97316' : '#eab308' }]}>
                            {c.severity}
                          </Text>
                        </View>
                        <Text style={styles.rankedDesc}>{c.description}</Text>
                        <Text style={styles.reporterName}>
                          👤 Reporter: @{c.username} • 🕒 {formattedTime} • Status: {c.status?.toUpperCase()}
                        </Text>
                      
                      {c.status === 'pending' && (
                        <View style={{ marginTop: 6 }}>
                          <TouchableOpacity 
                            style={styles.actionSelectorBtn}
                            onPress={() => setExpandedComplaintId(expandedComplaintId === c.id ? null : c.id!)}
                          >
                            <Text style={styles.actionSelectorBtnText}>
                              {expandedComplaintId === c.id ? "Close Options Menu" : "Take Action... (Options Menu)"}
                            </Text>
                          </TouchableOpacity>

                          {expandedComplaintId === c.id && (
                            <View style={styles.actionMenuContainer}>
                              <TouchableOpacity 
                                style={styles.actionMenuItem}
                                onPress={() => {
                                  setExpandedComplaintId(null);
                                  setActiveTab('map');
                                  handleLocationSelected(
                                    {
                                      confidence_score: 87.5,
                                      classification: "Flood",
                                      area_sq_km: 2.5,
                                      severity: c.severity,
                                      severity_score: c.score || 80,
                                      impact: { population: 3000, buildings: 120, facilities: 2 },
                                      mask_geojson: null
                                    },
                                    c.lat,
                                    c.lon
                                  );
                                }}
                              >
                                <Compass size={14} color="#2563eb" />
                                <Text style={styles.actionMenuText}>🛰️ Analyze Satellite Imagery & Flow</Text>
                              </TouchableOpacity>

                              <TouchableOpacity 
                                style={styles.actionMenuItem}
                                onPress={() => handleVoiceCallTrigger("+917678656930", c.severity)}
                              >
                                <PhoneCall size={14} color="#dc2626" />
                                <Text style={styles.actionMenuText}>📞 Trigger Twilio Voice Alert Call</Text>
                              </TouchableOpacity>

                              <TouchableOpacity 
                                style={styles.actionMenuItem}
                                onPress={() => handleEmailReportTrigger(c)}
                              >
                                <Mail size={14} color="#2563eb" />
                                <Text style={styles.actionMenuText}>📧 Send LLM RAG Situation Report</Text>
                              </TouchableOpacity>

                              <TouchableOpacity 
                                style={styles.actionMenuItem}
                                onPress={() => handleBroadcastNotification(c)}
                              >
                                <Bell size={14} color="#d97706" />
                                <Text style={styles.actionMenuText}>🔔 Broadcast Push Notification to Users</Text>
                              </TouchableOpacity>

                              <TouchableOpacity 
                                style={styles.actionMenuItem}
                                onPress={() => handleDeploySDRF(`${c.lat.toFixed(3)}N, ${c.lon.toFixed(3)}E`)}
                              >
                                <Users size={14} color="#10b981" />
                                <Text style={styles.actionMenuText}>🚀 Deploy SDRF Rescue Team</Text>
                              </TouchableOpacity>

                              <TouchableOpacity 
                                style={[styles.actionMenuItem, { borderBottomWidth: 0 }]}
                                onPress={() => handleResolveComplaint(c.id!)}
                              >
                                <Check size={14} color="#065f46" />
                                <Text style={[styles.actionMenuText, { color: '#065f46' }]}>✅ Mark Warning Resolved</Text>
                              </TouchableOpacity>
                            </View>
                          )}
                        </View>
                      )}
                    </View>
                  )})
                )}
              </View>
            </ScrollView>
          )
        )}

        {activeTab === 'agent' && role === 'official' && (
          <AgentPanel 
            lastResult={lastResult} 
            activeLat={activeLat} 
            activeLon={activeLon} 
          />
        )}

        {activeTab === 'settings' && (
          <SettingsPanel />
        )}
      </View>

      {/* Navigation Tab Bar */}
      <View style={styles.tabBar}>
        <TouchableOpacity 
          style={[styles.tabItem, activeTab === 'map' && styles.tabActive]}
          onPress={() => setActiveTab('map')}
        >
          <Map size={20} color={activeTab === 'map' ? '#2563eb' : '#64748b'} />
          <Text style={[styles.tabLabel, activeTab === 'map' && styles.tabLabelActive]}>Map</Text>
        </TouchableOpacity>

        <TouchableOpacity 
          style={[styles.tabItem, activeTab === 'report' && styles.tabActive]}
          onPress={() => setActiveTab('report')}
        >
          <Shield size={20} color={activeTab === 'report' ? '#2563eb' : '#64748b'} />
          <Text style={[styles.tabLabel, activeTab === 'report' && styles.tabLabelActive]}>
            {role === 'citizen' ? 'Safety Hub' : 'Warnings'}
          </Text>
        </TouchableOpacity>

        {role === 'citizen' && (
          <TouchableOpacity 
            style={[styles.tabItem, activeTab === 'raise' && styles.tabActive]}
            onPress={() => setActiveTab('raise')}
          >
            <PlusCircle size={20} color={activeTab === 'raise' ? '#ef4444' : '#64748b'} />
            <Text style={[styles.tabLabel, activeTab === 'raise' && styles.tabLabelActive]}>Raise Issue</Text>
          </TouchableOpacity>
        )}

        {role === 'official' && (
          <TouchableOpacity 
            style={[styles.tabItem, activeTab === 'agent' && styles.tabActive]}
            onPress={() => setActiveTab('agent')}
          >
            <Cpu size={20} color={activeTab === 'agent' ? '#10b981' : '#64748b'} />
            <Text style={[styles.tabLabel, activeTab === 'agent' && styles.tabLabelActive]}>AI Agent</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity 
          style={[styles.tabItem, activeTab === 'settings' && styles.tabActive]}
          onPress={() => setActiveTab('settings')}
        >
          <SettingsIcon size={20} color={activeTab === 'settings' ? '#2563eb' : '#64748b'} />
          <Text style={[styles.tabLabel, activeTab === 'settings' && styles.tabLabelActive]}>Settings</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  authErrorBox: {
    backgroundColor: '#fef2f2',
    borderWidth: 1,
    borderColor: '#fca5a5',
    borderRadius: 8,
    padding: 10,
    marginBottom: 16
  },
  authErrorText: {
    color: '#ef4444',
    fontSize: 11,
    fontWeight: 'bold',
    textAlign: 'center'
  },
  loginContainer: {
    flex: 1,
    backgroundColor: '#f8fafc',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 24
  },
  logoHeader: {
    alignItems: 'center',
    marginBottom: 32
  },
  logoTitle: {
    color: '#0f172a',
    fontSize: 28,
    fontWeight: '900',
    letterSpacing: 3
  },
  logoSubtitle: {
    color: '#64748b',
    fontSize: 12,
    marginTop: 6,
    fontWeight: '600'
  },
  authCard: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 24,
    width: '100%',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 10,
    elevation: 3
  },
  authTitle: {
    color: '#0f172a',
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 20,
    textAlign: 'center'
  },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingHorizontal: 12,
    height: 42,
    marginBottom: 12
  },
  authInput: {
    flex: 1,
    color: '#0f172a',
    fontSize: 13,
    height: '100%'
  },
  authLabel: {
    color: '#475569',
    fontSize: 12,
    fontWeight: 'bold',
    marginBottom: 8
  },
  roleChoiceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16
  },
  roleSelectBtn: {
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    borderRadius: 8,
    height: 38,
    width: '48%',
    justifyContent: 'center',
    alignItems: 'center'
  },
  roleSelectBtnText: {
    color: '#64748b',
    fontSize: 11,
    fontWeight: '600'
  },
  authSubmitBtn: {
    backgroundColor: '#2563eb',
    borderRadius: 8,
    height: 42,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8,
    shadowColor: '#2563eb',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 5
  },
  authSubmitBtnText: {
    color: '#ffffff',
    fontSize: 14,
    fontWeight: 'bold'
  },
  authToggleBtn: {
    marginTop: 16,
    alignItems: 'center'
  },
  authToggleBtnText: {
    color: '#2563eb',
    fontSize: 12,
    fontWeight: '600'
  },
  safeContainer: {
    flex: 1,
    backgroundColor: '#f8fafc',
    position: 'relative'
  },
  appHeader: {
    height: 56,
    backgroundColor: '#ffffff',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#e2e8f0'
  },
  headerTitleCol: {
    flexDirection: 'column'
  },
  headerTitle: {
    color: '#0f172a',
    fontSize: 15,
    fontWeight: '900',
    letterSpacing: 1
  },
  headerSubtitle: {
    color: '#64748b',
    fontSize: 10
  },
  headerRightCol: {
    flexDirection: 'row',
    alignItems: 'center'
  },
  badge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderWidth: 1,
    marginRight: 10
  },
  badgeText: {
    fontSize: 8,
    fontWeight: '900'
  },
  logoutBtn: {
    padding: 6
  },
  contentBody: {
    flex: 1
  },
  dashboardContainer: {
    flex: 1,
    backgroundColor: '#f8fafc',
    paddingHorizontal: 16,
    paddingTop: 16,
    ...Platform.select({
      web: {
        overflowY: 'auto'
      } as any
    })
  },
  hubGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16,
    flexWrap: 'wrap'
  },
  hubCard: {
    width: '48%',
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 14,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    flexDirection: 'column',
    alignItems: 'flex-start',
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1
  },
  hubIconBg: {
    width: 36,
    height: 36,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10
  },
  hubTextCol: {
    flexDirection: 'column'
  },
  hubCardTitle: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: 'bold',
    marginBottom: 4
  },
  hubCardDesc: {
    color: '#64748b',
    fontSize: 9,
    lineHeight: 12
  },
  notificationToast: {
    position: 'absolute',
    top: 10,
    left: 16,
    right: 16,
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 6,
    zIndex: 9999
  },
  toastTitle: {
    fontSize: 12,
    fontWeight: 'bold'
  },
  toastMessage: {
    fontSize: 10,
    marginTop: 2,
    lineHeight: 13
  },
  chatbotContainer: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    marginBottom: 16,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1
  },
  chatbotHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12
  },
  chatbotTitle: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: 'bold',
    marginLeft: 6
  },
  chatHistoryScroll: {
    maxHeight: 140,
    marginBottom: 12,
    backgroundColor: '#f8fafc',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0'
  },
  chatBubbleGroup: {
    marginBottom: 8
  },
  userBubble: {
    alignSelf: 'flex-end',
    backgroundColor: '#dbeafe',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    maxWidth: '80%'
  },
  userBubbleText: {
    color: '#1e40af',
    fontSize: 11,
    fontWeight: '500'
  },
  botBubble: {
    alignSelf: 'flex-start',
    backgroundColor: '#d1fae5',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    maxWidth: '80%',
    marginTop: 4
  },
  botBubbleText: {
    color: '#065f46',
    fontSize: 11,
    lineHeight: 15
  },
  chatInputRow: {
    flexDirection: 'row',
    alignItems: 'center'
  },
  chatInput: {
    flex: 1,
    backgroundColor: '#ffffff',
    color: '#0f172a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingHorizontal: 12,
    fontSize: 11,
    height: 38,
    marginRight: 8
  },
  chatSendBtn: {
    backgroundColor: '#2563eb',
    borderRadius: 8,
    paddingHorizontal: 14,
    height: 38,
    justifyContent: 'center',
    alignItems: 'center'
  },
  chatSendText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: 'bold'
  },
  testAlertBtn: {
    backgroundColor: '#ef4444',
    borderRadius: 10,
    height: 38,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16
  },
  testAlertText: {
    color: '#ffffff',
    fontSize: 11,
    fontWeight: 'bold'
  },
  emailConfigInput: {
    backgroundColor: '#ffffff',
    color: '#0f172a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingHorizontal: 12,
    height: 38,
    fontSize: 11
  },
  panelCard: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    marginBottom: 16,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10
  },
  cardTitle: {
    color: '#0f172a',
    fontSize: 13,
    fontWeight: 'bold',
    marginLeft: 8
  },
  helperText: {
    color: '#64748b',
    fontSize: 11,
    marginBottom: 12,
    lineHeight: 15
  },
  noDataText: {
    color: '#64748b',
    fontSize: 11,
    textAlign: 'center',
    paddingVertical: 10
  },
  alertItem: {
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
    paddingVertical: 10
  },
  alertItemTime: {
    color: '#ef4444',
    fontSize: 9,
    fontWeight: 'bold',
    marginBottom: 2
  },
  alertItemText: {
    color: '#334155',
    fontSize: 11,
    lineHeight: 15
  },
  logRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
    paddingVertical: 12
  },
  logRowLeft: {
    flex: 1.8,
    paddingRight: 8
  },
  logLocation: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: 'bold'
  },
  logDesc: {
    color: '#64748b',
    fontSize: 10,
    marginTop: 2
  },
  logRowRight: {
    flex: 1,
    alignItems: 'flex-end'
  },
  statusTag: {
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    marginBottom: 4
  },
  statusText: {
    fontSize: 8,
    fontWeight: 'bold'
  },
  logModelStatus: {
    color: '#10b981',
    fontSize: 9,
    fontWeight: 'bold'
  },
  statsCardRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16
  },
  statBox: {
    width: '48%',
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    alignItems: 'center',
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1
  },
  statNumber: {
    fontSize: 32,
    color: '#f59e0b',
    fontWeight: '900'
  },
  statLabel: {
    color: '#64748b',
    fontSize: 10,
    marginTop: 4
  },
  groupRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9'
  },
  groupLocName: {
    color: '#334155',
    fontSize: 12
  },
  groupCountBadge: {
    backgroundColor: '#dbeafe',
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 2
  },
  groupCountText: {
    color: '#1e40af',
    fontSize: 9,
    fontWeight: 'bold'
  },
  filterCard: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    marginBottom: 16,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 6,
    elevation: 1
  },
  filterHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10
  },
  filterTitle: {
    color: '#475569',
    fontSize: 11,
    fontWeight: 'bold',
    marginLeft: 6
  },
  filterOptionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8
  },
  filterLabelSmall: {
    color: '#64748b',
    fontSize: 11,
    width: 60
  },
  filterBtn: {
    backgroundColor: '#f8fafc',
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    marginRight: 6,
    borderWidth: 1,
    borderColor: '#e2e8f0'
  },
  filterBtnActive: {
    backgroundColor: '#2563eb',
    borderColor: '#2563eb'
  },
  filterBtnText: {
    color: '#64748b',
    fontSize: 9,
    fontWeight: 'bold'
  },
  filterBtnTextActive: {
    color: '#ffffff'
  },
  rankedRow: {
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    marginBottom: 12
  },
  rankedRowTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6
  },
  rankedBadge: {
    backgroundColor: '#f3e8ff',
    borderColor: '#c084fc',
    borderWidth: 0.5,
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2
  },
  rankedBadgeText: {
    color: '#6b21a8',
    fontSize: 9,
    fontWeight: 'bold'
  },
  rankedLocText: {
    color: '#0f172a',
    fontSize: 11,
    fontWeight: 'bold'
  },
  rankedSevText: {
    fontSize: 10,
    fontWeight: 'bold'
  },
  rankedDesc: {
    color: '#475569',
    fontSize: 11,
    lineHeight: 15,
    marginBottom: 6
  },
  reporterName: {
    color: '#64748b',
    fontSize: 9,
    marginBottom: 10
  },
  actionSelectorBtn: {
    backgroundColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    height: 36,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 8
  },
  actionSelectorBtnText: {
    color: '#0f172a',
    fontSize: 11,
    fontWeight: 'bold'
  },
  actionMenuContainer: {
    backgroundColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    padding: 8,
    marginTop: 8,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 5
  },
  actionMenuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
    paddingHorizontal: 8
  },
  actionMenuText: {
    color: '#334155',
    fontSize: 11,
    fontWeight: 'bold',
    marginLeft: 10
  },
  reportBulletin: {
    paddingVertical: 4
  },
  reportSummaryTitle: {
    fontSize: 12,
    fontWeight: 'bold',
    color: '#0f172a'
  },
  reportSummaryMeta: {
    fontSize: 10,
    color: '#64748b',
    marginTop: 2
  },
  reportDivider: {
    height: 1,
    backgroundColor: '#cbd5e1',
    marginVertical: 10
  },
  reportSectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 8
  },
  reportSectionIconBg: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#cbd5e1',
    justifyContent: 'center',
    alignItems: 'center'
  },
  reportSectionLabel: {
    fontSize: 9,
    fontWeight: 'bold',
    color: '#475569'
  },
  reportSectionValue: {
    fontSize: 11,
    fontWeight: 'bold',
    color: '#0f172a',
    marginTop: 2
  },
  reportProgressBarBg: {
    height: 6,
    backgroundColor: '#cbd5e1',
    borderRadius: 3,
    marginTop: 6,
    overflow: 'hidden'
  },
  reportProgressBar: {
    height: '100%'
  },
  infraStatusRow: {
    marginTop: 4
  },
  infraStatusDot: {
    fontSize: 10,
    fontWeight: 'bold',
    marginVertical: 2
  },
  recommendationsBlock: {
    backgroundColor: '#fef2f2',
    borderRadius: 8,
    padding: 10,
    marginTop: 12,
    borderWidth: 1,
    borderColor: '#fca5a5'
  },
  recommendationsTitle: {
    fontSize: 10,
    fontWeight: 'bold',
    color: '#991b1b'
  },
  recommendationsText: {
    fontSize: 10,
    color: '#7f1d1d',
    marginTop: 4,
    lineHeight: 14
  },
  tabBar: {
    height: 60,
    backgroundColor: '#ffffff',
    borderTopWidth: 1,
    borderTopColor: '#e2e8f0',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingBottom: 6
  },
  tabItem: {
    alignItems: 'center',
    justifyContent: 'center',
    flex: 1,
    height: '100%',
    paddingTop: 8
  },
  tabActive: {
    borderTopWidth: 3,
    borderTopColor: '#2563eb'
  },
  tabLabel: {
    color: '#64748b',
    fontSize: 10,
    marginTop: 4,
    fontWeight: '500'
  },
  tabLabelActive: {
    fontWeight: 'bold',
    color: '#2563eb'
  }
});
