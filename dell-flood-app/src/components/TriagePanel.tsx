import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Modal,
  TextInput,
  Platform,
  Alert,
} from 'react-native';
import {
  ShieldAlert,
  Users,
  Home,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sliders,
  FileSpreadsheet,
  Activity,
  ChevronRight,
  PlusCircle,
  XCircle,
  Zap,
} from 'lucide-react-native';
import { apiService } from '../services/api';

interface ClusterProfile {
  cluster_id: string;
  county_name: string;
  population: number;
  exposure: number;
  twi_risk_tier: string;
  elevation_safety: number;
  priority_score: number;
  rank: number;
  assigned_shelters: Array<{
    shelter_name: string;
    allocated_population: number;
    shelter_type: string;
    status: string;
  }>;
  unallocated_population: number;
}

interface ShelterProfile {
  shelter_id: string;
  name: string;
  county: string;
  capacity: number;
  remaining_capacity: number;
  shelter_type: string;
  status: string;
}

export const TriagePanel: React.FC = () => {
  const [threadId, setThreadId] = useState<string>('');
  const [clusters, setClusters] = useState<ClusterProfile[]>([]);
  const [shelters, setShelters] = useState<ShelterProfile[]>([]);
  const [unallocatedTotal, setUnallocatedTotal] = useState<number>(0);
  const [auditLogs, setAuditLogs] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(false);

  // Override Modal States
  const [modalVisible, setModalVisible] = useState<boolean>(false);
  const [overrideAction, setOverrideAction] = useState<'SHELTER_FULL' | 'ROAD_CLOSED' | 'FORCE_PRIORITY'>('SHELTER_FULL');
  const [selectedShelterName, setSelectedShelterName] = useState<string>('Athens Community Center');
  const [overrideReason, setOverrideReason] = useState<string>('Operator field telemetry: capacity saturated');

  const fetchTriage = async () => {
    setLoading(true);
    try {
      const res = await apiService.runTriage('Athens County, Ohio');
      if (res && (res.status === 'AWAITING_OPERATOR_REVIEW' || res.status === 'SUCCESS' || res.priority_queue)) {
        setThreadId(res.thread_id || 'thread_athens');
        setClusters(res.priority_queue || []);
        setShelters(res.shelter_allocations || []);
        setUnallocatedTotal(res.unallocated_count || 0);
        setAuditLogs(res.audit_log || []);
      }
    } catch (e: any) {
      console.log('[Triage Fetch Error]', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTriage();
  }, []);

  const handleApplyOverride = async () => {
    if (!threadId) {
      Alert.alert('No Active Thread', 'Please run a triage cycle first.');
      return;
    }

    setLoading(true);
    setModalVisible(false);

    try {
      const overrides = [
        {
          action_type: overrideAction,
          target_id: selectedShelterName,
          reason: overrideReason,
        },
      ];

      const res = await apiService.applyTriageOverride(threadId, overrides);
      if (res && (res.status === 'COMPLETED' || res.priority_queue)) {
        setClusters(res.priority_queue || []);
        setShelters(res.shelter_allocations || []);
        setUnallocatedTotal(res.unallocated_count || 0);
        setAuditLogs(res.audit_log || []);
      }
    } catch (e: any) {
      console.log('[Triage Override Error]', e);
      Alert.alert('Override Error', e?.message || 'Failed to submit override.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <ShieldAlert size={20} color="#38bdf8" />
          <View>
            <Text style={styles.headerTitle}>Multi-Criteria Disaster Triage Hub</Text>
            <Text style={styles.headerSubtitle}>
              LangGraph StateGraph • Thread: {threadId || 'Initial'}
            </Text>
          </View>
        </View>

        <TouchableOpacity style={styles.refreshBtn} onPress={fetchTriage} disabled={loading}>
          {loading ? (
            <ActivityIndicator size="small" color="#38bdf8" />
          ) : (
            <RotateCcw size={16} color="#38bdf8" />
          )}
          <Text style={styles.refreshBtnText}>Re-Run Triage</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.kpiContainer}>
        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>Rank #1 County</Text>
          <Text style={[styles.kpiValue, { color: '#f87171' }]} numberOfLines={1}>
            {clusters[0]?.county_name ? clusters[0].county_name.split(',')[0] : 'Athens County'}
          </Text>
          <Text style={styles.kpiSub}>Score: {clusters[0]?.priority_score ? clusters[0].priority_score.toFixed(1) : '197.3'}</Text>
        </View>

        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>Monitored Clusters</Text>
          <Text style={styles.kpiValue}>{clusters.length || 30}</Text>
          <Text style={styles.kpiSub}>Across 30 Counties</Text>
        </View>

        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>Shelter Network</Text>
          <Text style={[styles.kpiValue, { color: '#38bdf8' }]}>{shelters.length || 71}</Text>
          <Text style={styles.kpiSub}>Active Facilities</Text>
        </View>

        <View style={styles.kpiCard}>
          <Text style={styles.kpiLabel}>Unallocated Pop</Text>
          <Text
            style={[
              styles.kpiValue,
              { color: unallocatedTotal === 0 ? '#34d399' : '#f87171' },
            ]}
          >
            {unallocatedTotal}
          </Text>
          <Text style={styles.kpiSub}>{unallocatedTotal === 0 ? '100% Safe Placement' : 'Overflow Warning'}</Text>
        </View>
      </View>

      <View style={styles.actionBar}>
        <Text style={styles.actionPromptText}>Operator Mid-Run Overrides:</Text>
        <View style={styles.actionButtonsRow}>
          <TouchableOpacity
            style={[styles.actionBtn, { backgroundColor: 'rgba(239, 68, 68, 0.15)', borderColor: '#ef4444' }]}
            onPress={() => {
              setOverrideAction('SHELTER_FULL');
              setSelectedShelterName('Athens Community Center');
              setModalVisible(true);
            }}
          >
            <XCircle size={14} color="#f87171" />
            <Text style={[styles.actionBtnText, { color: '#f87171' }]}>Mark Shelter Full</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, { backgroundColor: 'rgba(245, 158, 11, 0.15)', borderColor: '#f59e0b' }]}
            onPress={() => {
              setOverrideAction('ROAD_CLOSED');
              setSelectedShelterName('Route Corridor US-33');
              setModalVisible(true);
            }}
          >
            <AlertTriangle size={14} color="#fbbf24" />
            <Text style={[styles.actionBtnText, { color: '#fbbf24' }]}>Close Road Segment</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, { backgroundColor: 'rgba(168, 85, 247, 0.15)', borderColor: '#a855f7' }]}
            onPress={() => {
              setOverrideAction('FORCE_PRIORITY');
              setSelectedShelterName('Athens County, Ohio');
              setModalVisible(true);
            }}
          >
            <Zap size={14} color="#c084fc" />
            <Text style={[styles.actionBtnText, { color: '#c084fc' }]}>Force Priority</Text>
          </TouchableOpacity>
        </View>
      </View>

      <ScrollView style={styles.contentScroll} showsVerticalScrollIndicator={false}>
        <Text style={styles.sectionHeading}>Priority Urgency Queue [P × (1+E) / E_safety]</Text>
        <View style={styles.clusterList}>
          {clusters.slice(0, 10).map((c, index) => {
            const isRank1 = c.rank === 1 || index === 0;
            return (
              <View
                key={c.cluster_id || index}
                style={[styles.clusterCard, isRank1 && styles.rank1Card]}
              >
                <View style={styles.clusterHeaderRow}>
                  <View style={styles.rankBadge}>
                    <Text style={styles.rankText}>#{c.rank || index + 1}</Text>
                  </View>
                  <View style={styles.clusterTitleCol}>
                    <Text style={styles.clusterCountyName}>{c.county_name}</Text>
                    <Text style={styles.clusterMetricsSummary}>
                      Pop: {c.population} • Exposure: {(c.exposure * 100).toFixed(0)}% • Safety: {c.elevation_safety}
                    </Text>
                  </View>
                  <View style={styles.scoreBadge}>
                    <Text style={styles.scoreVal}>{c.priority_score.toFixed(1)}</Text>
                    <Text style={styles.scoreLabel}>Priority</Text>
                  </View>
                </View>

                <View style={styles.shelterAssignWrap}>
                  <Text style={styles.assignedTitle}>Allocated Shelters & Placement:</Text>
                  {c.assigned_shelters && c.assigned_shelters.length > 0 ? (
                    c.assigned_shelters.map((as, aIdx) => (
                      <View key={aIdx} style={styles.assignedShelterItem}>
                        <CheckCircle2 size={13} color="#34d399" />
                        <Text style={styles.assignedShelterName}>{as.shelter_name}</Text>
                        <Text style={styles.assignedShelterCount}>
                          +{as.allocated_population} citizens
                        </Text>
                      </View>
                    ))
                  ) : (
                    <Text style={styles.noShelterWarning}>Awaiting secondary rerouting</Text>
                  )}
                </View>
              </View>
            );
          })}
        </View>

        {auditLogs && auditLogs.length > 0 && (
          <View style={styles.auditSection}>
            <Text style={styles.sectionHeading}>Operator Audit Log & Course Corrections</Text>
            <View style={styles.auditBox}>
              {auditLogs.map((log, lIdx) => (
                <Text key={lIdx} style={styles.auditLogLine}>
                  {log}
                </Text>
              ))}
            </View>
          </View>
        )}
      </ScrollView>

      <Modal visible={modalVisible} transparent animationType="fade" onRequestClose={() => setModalVisible(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Submit Operator Override</Text>
              <TouchableOpacity onPress={() => setModalVisible(false)}>
                <XCircle size={20} color="#94a3b8" />
              </TouchableOpacity>
            </View>

            <Text style={styles.inputLabel}>Action Type</Text>
            <View style={styles.actionTypeDisplay}>
              <Text style={styles.actionTypeText}>{overrideAction}</Text>
            </View>

            <Text style={styles.inputLabel}>Target Facility / Location</Text>
            <TextInput
              style={styles.modalInput}
              value={selectedShelterName}
              onChangeText={setSelectedShelterName}
              placeholder="e.g. Athens Community Center"
              placeholderTextColor="#64748b"
            />

            <Text style={styles.inputLabel}>Operational Reason</Text>
            <TextInput
              style={[styles.modalInput, { height: 70 }]}
              value={overrideReason}
              onChangeText={setOverrideReason}
              multiline
              placeholder="Reason for manual override"
              placeholderTextColor="#64748b"
            />

            <View style={styles.modalFooter}>
              <TouchableOpacity style={styles.cancelBtn} onPress={() => setModalVisible(false)}>
                <Text style={styles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.submitBtn} onPress={handleApplyOverride}>
                <Text style={styles.submitBtnText}>Execute Override</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#090d16',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    backgroundColor: '#0f172a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  headerTitle: {
    color: '#f8fafc',
    fontSize: 15,
    fontWeight: '700',
  },
  headerSubtitle: {
    color: '#94a3b8',
    fontSize: 11,
  },
  refreshBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(56, 189, 248, 0.1)',
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.3)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  refreshBtnText: {
    color: '#38bdf8',
    fontSize: 12,
    fontWeight: '600',
  },
  kpiContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    gap: 8,
    backgroundColor: '#0f172a',
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
  },
  kpiCard: {
    flex: 1,
    backgroundColor: '#1e293b',
    borderRadius: 10,
    padding: 10,
    borderWidth: 1,
    borderColor: '#334155',
  },
  kpiLabel: {
    color: '#94a3b8',
    fontSize: 10,
    textTransform: 'uppercase',
    marginBottom: 2,
  },
  kpiValue: {
    color: '#f8fafc',
    fontSize: 14,
    fontWeight: '700',
  },
  kpiSub: {
    color: '#64748b',
    fontSize: 10,
    marginTop: 2,
  },
  actionBar: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#131d31',
    borderBottomWidth: 1,
    borderBottomColor: '#1e293b',
  },
  actionPromptText: {
    color: '#94a3b8',
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  actionButtonsRow: {
    flexDirection: 'row',
    gap: 8,
  },
  actionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  actionBtnText: {
    fontSize: 11,
    fontWeight: '700',
  },
  contentScroll: {
    flex: 1,
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  sectionHeading: {
    color: '#f8fafc',
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 12,
    marginTop: 4,
  },
  clusterList: {
    gap: 12,
  },
  clusterCard: {
    backgroundColor: '#1e293b',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1,
    borderColor: '#334155',
  },
  rank1Card: {
    borderColor: 'rgba(239, 68, 68, 0.5)',
    backgroundColor: '#231b26',
  },
  clusterHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  rankBadge: {
    backgroundColor: '#0284c7',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    marginRight: 10,
  },
  rankText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '800',
  },
  clusterTitleCol: {
    flex: 1,
  },
  clusterCountyName: {
    color: '#f8fafc',
    fontSize: 14,
    fontWeight: '700',
  },
  clusterMetricsSummary: {
    color: '#94a3b8',
    fontSize: 11,
    marginTop: 2,
  },
  scoreBadge: {
    alignItems: 'flex-end',
    backgroundColor: '#0f172a',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  scoreVal: {
    color: '#f87171',
    fontSize: 14,
    fontWeight: '800',
  },
  scoreLabel: {
    color: '#64748b',
    fontSize: 9,
    textTransform: 'uppercase',
  },
  shelterAssignWrap: {
    backgroundColor: '#0f172a',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: '#334155',
    gap: 6,
  },
  assignedTitle: {
    color: '#94a3b8',
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 2,
  },
  assignedShelterItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  assignedShelterName: {
    color: '#e2e8f0',
    fontSize: 12,
    flex: 1,
    marginLeft: 6,
  },
  assignedShelterCount: {
    color: '#34d399',
    fontSize: 12,
    fontWeight: '700',
  },
  noShelterWarning: {
    color: '#f87171',
    fontSize: 11,
  },
  auditSection: {
    marginTop: 20,
    marginBottom: 30,
  },
  auditBox: {
    backgroundColor: '#0f172a',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#334155',
    gap: 6,
  },
  auditLogLine: {
    color: '#cbd5e1',
    fontSize: 11,
    fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
    lineHeight: 16,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  modalContent: {
    width: '100%',
    maxWidth: 480,
    backgroundColor: '#1e293b',
    borderRadius: 14,
    padding: 20,
    borderWidth: 1,
    borderColor: '#334155',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  modalTitle: {
    color: '#f8fafc',
    fontSize: 16,
    fontWeight: '700',
  },
  inputLabel: {
    color: '#94a3b8',
    fontSize: 12,
    marginBottom: 6,
    marginTop: 10,
  },
  actionTypeDisplay: {
    backgroundColor: '#0f172a',
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  actionTypeText: {
    color: '#38bdf8',
    fontSize: 13,
    fontWeight: '700',
  },
  modalInput: {
    backgroundColor: '#0f172a',
    borderRadius: 8,
    padding: 10,
    color: '#f8fafc',
    fontSize: 13,
    borderWidth: 1,
    borderColor: '#334155',
  },
  modalFooter: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 20,
  },
  cancelBtn: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#334155',
  },
  cancelBtnText: {
    color: '#cbd5e1',
    fontSize: 13,
    fontWeight: '600',
  },
  submitBtn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 8,
    backgroundColor: '#0284c7',
  },
  submitBtnText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: '700',
  },
});

