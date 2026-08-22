import React, { useState } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, TextInput, ScrollView, ActivityIndicator, Alert, Platform } from 'react-native';
import { Bot, Terminal, RefreshCw, Check, AlertTriangle, ShieldCheck, Waves, CloudRain, Users, Home, Compass, MapPin } from 'lucide-react-native';
import { apiService, DetectionResult } from '../services/api';

interface AgentPanelProps {
  lastResult: DetectionResult | null;
  activeLat: number;
  activeLon: number;
}

interface AgentResultSummary {
  location: string;
  severity: string;
  classification: string;
  area_sq_km: number;
  rainfall_5day_mm: number;
  gauge_status: string;
  confidence: number;
  population: number;
  buildings: number;
}

const PRESET_DISTRICTS = [
  { name: 'Patna District', lat: 25.6124, lon: 85.1376 },
  { name: 'Golaghat', lat: 26.5239, lon: 93.9632 },
  { name: 'Cachar', lat: 24.8333, lon: 92.7667 },
  { name: 'Jorhat', lat: 26.7509, lon: 94.2037 },
  { name: 'Majuli Island', lat: 26.9601, lon: 94.1802 },
  { name: 'Charaideo', lat: 27.0270, lon: 94.8872 },
  { name: 'Kaziranga', lat: 26.5775, lon: 93.1711 },
];

export const AgentPanel: React.FC<AgentPanelProps> = ({ lastResult, activeLat, activeLon }) => {
  const [locationName, setLocationName] = useState<string>('Patna District');
  const [runningAgent, setRunningAgent] = useState<boolean>(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [report, setReport] = useState<string>('');
  const [summary, setSummary] = useState<AgentResultSummary | null>(null);

  const triggerAgent = async () => {
    if (!locationName.trim()) {
      Alert.alert('Error', 'Please enter a target location.');
      return;
    }
    setRunningAgent(true);
    setLogs([]);
    setReport('');
    setSummary(null);

    try {
      let targetLat = activeLat;
      let targetLon = activeLon;

      const matched = PRESET_DISTRICTS.find(
        d => d.name.toLowerCase() === locationName.toLowerCase()
      );
      if (matched) {
        targetLat = matched.lat;
        targetLon = matched.lon;
      } else {
        const geo = await apiService.geocodePlace(locationName);
        if (geo.status === 'SUCCESS' && typeof geo.lat === 'number' && typeof geo.lon === 'number') {
          targetLat = geo.lat;
          targetLon = geo.lon;
        }
      }

      const response = await apiService.runAgentCycle(locationName, targetLat, targetLon);

      const logList = response.logs || response.result?.logs || [];
      const reportText = response.report || response.result?.report || '';
      const resultObj = response.result || response;

      if (logList.length > 0) {
        setLogs(logList);
        setReport(reportText);
        setSummary({
          location: resultObj.location || locationName,
          severity: resultObj.severity || 'NONE',
          classification: resultObj.classification || 'Normal Conditions / Dry Ground',
          area_sq_km: resultObj.area_sq_km || 0.0,
          rainfall_5day_mm: resultObj.rainfall_5day_mm || 0.0,
          gauge_status: resultObj.gauge_status || 'NORMAL',
          confidence: resultObj.confidence || 0,
          population: resultObj.population || 0,
          buildings: resultObj.buildings || 0,
        });
      } else {
        // Fallback trace check
        const trace = await apiService.getAgentTrace(locationName);
        if (trace && trace.logs && trace.logs.length > 0) {
          setLogs(trace.logs);
          setReport(trace.report || '');
          setSummary({
            location: trace.location || locationName,
            severity: trace.severity || 'NONE',
            classification: trace.classification || 'Normal Conditions / Dry Ground',
            area_sq_km: trace.area_sq_km || 0.0,
            rainfall_5day_mm: trace.rainfall_5day_mm || 0.0,
            gauge_status: trace.gauge_status || 'NORMAL',
            confidence: trace.confidence || 0,
            population: trace.population || 0,
            buildings: trace.buildings || 0,
          });
        }
      }
    } catch (e: any) {
      Alert.alert('Execution Notice', e.message || 'Agent cycle completed with fallback telemetry.');
    } finally {
      setRunningAgent(false);
    }
  };

  const getLogColor = (line: string) => {
    if (line.includes('CRITICAL') || line.includes('DANGER') || line.includes('ALERT') || line.includes('Catastrophic')) {
      return '#f87171'; // Red
    }
    if (line.includes('WARNING') || line.includes('HIGH') || line.includes('Threshold exceeded')) {
      return '#fbbf24'; // Yellow
    }
    if (line.includes('STEP') || line.includes('START') || line.includes('COMPLETE')) {
      return '#38bdf8'; // Sky blue
    }
    if (line.includes('SegFormer') || line.includes('Sentinel') || line.includes('NDWI') || line.includes('ML')) {
      return '#c084fc'; // Purple
    }
    return '#4ade80'; // Bright Green
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 40 }}>
      {/* 1. Agent Controller Card */}
      <View style={styles.card}>
        <View style={styles.header}>
          <Bot size={22} color="#10b981" />
          <Text style={styles.title}>Autonomous Agent Monitor</Text>
        </View>
        <Text style={styles.subtitle}>
          Trigger the FloodAgent loop to autonomously fetch coordinates, query real-time OpenWeather 5-day forecasts, evaluate CWC gauges, run satellite bands + SegFormer ML, and generate situation bulletins.
        </Text>

        {/* District Quick-Select Chips */}
        <Text style={styles.chipsLabel}>Quick Select Target District:</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipsScroll}>
          {PRESET_DISTRICTS.map((d, i) => (
            <TouchableOpacity
              key={i}
              style={[
                styles.chip,
                locationName.toLowerCase() === d.name.toLowerCase() && styles.activeChip
              ]}
              onPress={() => setLocationName(d.name)}
            >
              <MapPin size={11} color={locationName.toLowerCase() === d.name.toLowerCase() ? '#ffffff' : '#64748b'} style={{ marginRight: 4 }} />
              <Text
                style={[
                  styles.chipText,
                  locationName.toLowerCase() === d.name.toLowerCase() && styles.activeChipText
                ]}
              >
                {d.name}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        
        <View style={styles.row}>
          <TextInput
            style={styles.input}
            value={locationName}
            onChangeText={setLocationName}
            placeholder="Target Area Name..."
            placeholderTextColor="#94a3b8"
          />
          <TouchableOpacity style={styles.triggerButton} onPress={triggerAgent} disabled={runningAgent}>
            {runningAgent ? (
              <>
                <ActivityIndicator size="small" color="#ffffff" style={{ marginRight: 6 }} />
                <Text style={styles.buttonText}>Running Pipeline...</Text>
              </>
            ) : (
              <>
                <RefreshCw size={14} color="#ffffff" style={{ marginRight: 6 }} />
                <Text style={styles.buttonText}>Run Cycle</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {/* Live Logs Console */}
        {logs.length > 0 && (
          <View style={styles.consoleContainer}>
            <View style={styles.consoleHeader}>
              <Terminal size={14} color="#10b981" />
              <Text style={styles.consoleTitle}>Decision Trace & Pipeline Execution Logs</Text>
              <View style={styles.liveBadge}>
                <Text style={styles.liveBadgeText}>COMPLETED</Text>
              </View>
            </View>
            <ScrollView style={styles.consoleScroll} nestedScrollEnabled={true}>
              {logs.map((logStr, idx) => (
                <Text key={idx} style={[styles.consoleText, { color: getLogColor(logStr) }]}>
                  {logStr}
                </Text>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Metric Summary Cards (Shown when result is available) */}
        {summary && (
          <View style={styles.summaryContainer}>
            <View style={styles.summaryHeader}>
              <Text style={styles.summaryTitle}>Assessment Summary: {summary.location}</Text>
              <View
                style={[
                  styles.severityBadge,
                  {
                    backgroundColor:
                      summary.severity === 'CRITICAL' ? '#fee2e2' :
                      summary.severity === 'HIGH' ? '#fef3c7' :
                      summary.severity === 'MODERATE' ? '#e0f2fe' : '#f0fdf4'
                  }
                ]}
              >
                <Text
                  style={[
                    styles.severityBadgeText,
                    {
                      color:
                        summary.severity === 'CRITICAL' ? '#dc2626' :
                        summary.severity === 'HIGH' ? '#b45309' :
                        summary.severity === 'MODERATE' ? '#0284c7' : '#16a34a'
                    }
                  ]}
                >
                  {summary.severity} SEVERITY
                </Text>
              </View>
            </View>

            <View style={styles.kpiGrid}>
              <View style={styles.kpiCard}>
                <CloudRain size={16} color="#0284c7" />
                <Text style={styles.kpiValue}>{summary.rainfall_5day_mm} mm</Text>
                <Text style={styles.kpiLabel}>5-Day Rainfall</Text>
              </View>

              <View style={styles.kpiCard}>
                <Waves size={16} color={summary.gauge_status === 'DANGER' ? '#dc2626' : summary.gauge_status === 'WARNING' ? '#d97706' : '#16a34a'} />
                <Text style={[styles.kpiValue, { color: summary.gauge_status === 'DANGER' ? '#dc2626' : summary.gauge_status === 'WARNING' ? '#d97706' : '#16a34a' }]}>
                  {summary.gauge_status}
                </Text>
                <Text style={styles.kpiLabel}>CWC Gauge Status</Text>
              </View>

              <View style={styles.kpiCard}>
                <Compass size={16} color="#7c3aed" />
                <Text style={styles.kpiValue}>{summary.area_sq_km} km²</Text>
                <Text style={styles.kpiLabel}>Flooded Area</Text>
              </View>

              <View style={styles.kpiCard}>
                <Users size={16} color="#ea580c" />
                <Text style={styles.kpiValue}>{summary.population.toLocaleString()}</Text>
                <Text style={styles.kpiLabel}>Population at Risk</Text>
              </View>
            </View>
          </View>
        )}

        {/* Generated Situation Report Output */}
        {report.length > 0 && (
          <View style={styles.reportContainer}>
            <View style={styles.reportHeader}>
              <Check size={14} color="#10b981" style={{ marginRight: 6 }} />
              <Text style={styles.reportTitle}>Agent Situation Bulletin Report</Text>
            </View>
            <ScrollView style={{ maxHeight: 220 }} nestedScrollEnabled={true}>
              <Text style={styles.reportText}>{report}</Text>
            </ScrollView>
          </View>
        )}
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
    padding: 16
  },
  card: {
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
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8
  },
  title: {
    color: '#0f172a',
    fontSize: 16,
    fontWeight: 'bold',
    marginLeft: 8
  },
  subtitle: {
    color: '#64748b',
    fontSize: 12,
    marginBottom: 12,
    lineHeight: 16
  },
  chipsLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#475569',
    marginBottom: 6
  },
  chipsScroll: {
    flexDirection: 'row',
    marginBottom: 12
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f1f5f9',
    borderRadius: 16,
    paddingHorizontal: 10,
    paddingVertical: 5,
    marginRight: 6,
    borderWidth: 1,
    borderColor: '#e2e8f0'
  },
  activeChip: {
    backgroundColor: '#10b981',
    borderColor: '#059669'
  },
  chipText: {
    fontSize: 11,
    color: '#475569',
    fontWeight: '500'
  },
  activeChipText: {
    color: '#ffffff',
    fontWeight: '700'
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12
  },
  input: {
    flex: 1,
    backgroundColor: '#ffffff',
    color: '#0f172a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingHorizontal: 12,
    height: 42,
    fontSize: 13,
    marginRight: 10
  },
  triggerButton: {
    backgroundColor: '#10b981',
    borderRadius: 8,
    paddingHorizontal: 14,
    height: 42,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center'
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: 'bold'
  },
  consoleContainer: {
    backgroundColor: '#090d16',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#1e293b',
    padding: 12,
    marginTop: 12
  },
  consoleHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
    paddingBottom: 6
  },
  consoleTitle: {
    color: '#10b981',
    fontSize: 11,
    fontWeight: 'bold',
    marginLeft: 6,
    flex: 1
  },
  liveBadge: {
    backgroundColor: '#064e3b',
    borderRadius: 4,
    paddingHorizontal: 6,
    paddingVertical: 2
  },
  liveBadgeText: {
    color: '#34d399',
    fontSize: 9,
    fontWeight: 'bold'
  },
  consoleScroll: {
    maxHeight: 200
  },
  consoleText: {
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    fontSize: 10,
    lineHeight: 15,
    marginBottom: 3
  },
  summaryContainer: {
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    padding: 12,
    marginTop: 12
  },
  summaryHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10
  },
  summaryTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#0f172a'
  },
  severityBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3
  },
  severityBadgeText: {
    fontSize: 10,
    fontWeight: 'bold'
  },
  kpiGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8
  },
  kpiCard: {
    flex: 1,
    minWidth: 100,
    backgroundColor: '#ffffff',
    borderRadius: 8,
    padding: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    alignItems: 'center'
  },
  kpiValue: {
    fontSize: 13,
    fontWeight: 'bold',
    color: '#0f172a',
    marginTop: 4
  },
  kpiLabel: {
    fontSize: 9,
    color: '#64748b',
    marginTop: 2
  },
  reportContainer: {
    backgroundColor: '#f8fafc',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    padding: 12,
    marginTop: 12
  },
  reportHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8
  },
  reportTitle: {
    color: '#0f172a',
    fontSize: 12,
    fontWeight: 'bold'
  },
  reportText: {
    color: '#334155',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    lineHeight: 16
  }
});
