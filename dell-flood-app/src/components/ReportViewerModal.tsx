import React from 'react';
import { View, Text, StyleSheet, Modal, TouchableOpacity, ScrollView, Platform, Linking, ActivityIndicator } from 'react-native';
import { Download, X, FileText, CheckCircle2, ShieldAlert, Share2 } from 'lucide-react-native';

interface ReportViewerModalProps {
  visible: boolean;
  onClose: () => void;
  reportText?: string;
  location?: string;
  lat?: number;
  lon?: number;
  area?: number;
  classification?: string;
  severity?: string;
  pop?: number;
  bld?: number;
  fac?: number;
  conf?: number;
  pdfDownloadUrl?: string;
}

export const ReportViewerModal: React.FC<ReportViewerModalProps> = ({
  visible,
  onClose,
  reportText,
  location = 'Regional Scan Area',
  lat = 29.3013,
  lon = -94.7977,
  area = 12.5,
  classification = 'Inundation',
  severity = 'HIGH',
  pop = 12500,
  bld = 1850,
  fac = 4,
  conf = 94.2,
  pdfDownloadUrl,
}) => {
  const handleDownloadPdf = () => {
    if (pdfDownloadUrl) {
      if (Platform.OS === 'web') {
        window.open(pdfDownloadUrl, '_blank');
      } else {
        Linking.openURL(pdfDownloadUrl).catch(err => console.log('Cannot open PDF URL:', err));
      }
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={true} onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.modalContainer}>
          {/* Header */}
          <View style={styles.header}>
            <View style={styles.headerTitleRow}>
              <FileText size={20} color="#38bdf8" />
              <Text style={styles.headerTitle}>Disaster Situation Bulletin</Text>
            </View>
            <TouchableOpacity style={styles.closeBtn} onPress={onClose}>
              <X size={20} color="#94a3b8" />
            </TouchableOpacity>
          </View>

          {/* Quick Metrics Bar */}
          <View style={styles.metricsBar}>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Location</Text>
              <Text style={styles.metricVal} numberOfLines={1}>{location}</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Severity</Text>
              <Text style={[styles.metricVal, { color: severity === 'HIGH' || severity === 'CRITICAL' ? '#f87171' : '#fbbf24' }]}>
                {severity}
              </Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Affected Pop</Text>
              <Text style={styles.metricVal}>{pop.toLocaleString()}</Text>
            </View>
            <View style={styles.metricItem}>
              <Text style={styles.metricLabel}>Confidence</Text>
              <Text style={[styles.metricVal, { color: '#34d399' }]}>{conf.toFixed(1)}%</Text>
            </View>
          </View>

          {/* Report Body */}
          <ScrollView style={styles.bodyScroll} contentContainerStyle={styles.bodyContent}>
            {reportText ? (
              <Text style={styles.reportText}>{reportText}</Text>
            ) : (
              <View style={styles.fallbackContainer}>
                <Text style={styles.sectionHeader}>1. SITUATION OVERVIEW</Text>
                <Text style={styles.paragraph}>
                  Satellite optical & SegFormer neural scans confirm an active {classification.toLowerCase()} event
                  covering approximately {area.toFixed(2)} sq km near {location} ({lat.toFixed(4)}°N, {lon.toFixed(4)}°E).
                  Estimated affected population is {pop.toLocaleString()} residents.
                </Text>

                <Text style={styles.sectionHeader}>2. INFRASTRUCTURE & MUNICIPAL EXPOSURE</Text>
                <Text style={styles.paragraph}>
                  Spatial building footprint overlays indicate {bld.toLocaleString()} inundated residential/commercial
                  structures. {fac} critical facilities (medical clinics, shelters, power stations) are under advisory.
                </Text>

                <Text style={styles.sectionHeader}>3. RESCUE & EVACUATION DIRECTIVES</Text>
                <Text style={styles.paragraph}>
                  • Direct vulnerable populations along elevation-weighted high-ground routes.
                  {'\n'}• Mobilize de-watering pumps to critical road corridor nodes.
                  {'\n'}• Verify capacity at nearest operational emergency shelters.
                </Text>
              </View>
            )}
          </ScrollView>

          {/* Footer Action Buttons */}
          <View style={styles.footer}>
            <TouchableOpacity style={styles.downloadBtn} onPress={handleDownloadPdf}>
              <Download size={18} color="#ffffff" />
              <Text style={styles.downloadBtnText}>Download Official PDF</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.secondaryBtn} onPress={onClose}>
              <Text style={styles.secondaryBtnText}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
 overlay: {
 flex: 1,
 backgroundColor: 'rgba(0, 0, 0, 0.75)',
 justifyContent: 'center',
 alignItems: 'center',
 padding: 16,
 },
 modalContainer: {
 width: '100%',
 maxWidth: 620,
 maxHeight: '90%',
 backgroundColor: '#0f172a',
 borderRadius: 16,
 borderWidth: 1,
 borderColor: '#334155',
 overflow: 'hidden',
 shadowColor: '#000',
 shadowOffset: { width: 0, height: 10 },
 shadowOpacity: 0.5,
 shadowRadius: 20,
 elevation: 10,
 },
 header: {
 flexDirection: 'row',
 alignItems: 'center',
 justifyContent: 'space-between',
 paddingHorizontal: 20,
 paddingVertical: 16,
 backgroundColor: '#1e293b',
 borderBottomWidth: 1,
 borderBottomColor: '#334155',
 },
 headerTitleRow: {
 flexDirection: 'row',
 alignItems: 'center',
 gap: 10,
 },
 headerTitle: {
 color: '#f8fafc',
 fontSize: 16,
 fontWeight: '700',
 letterSpacing: 0.5,
 },
 closeBtn: {
 padding: 6,
 borderRadius: 8,
 backgroundColor: '#334155',
 },
 metricsBar: {
 flexDirection: 'row',
 backgroundColor: '#1e293b',
 paddingHorizontal: 16,
 paddingVertical: 12,
 borderBottomWidth: 1,
 borderBottomColor: '#334155',
 justifyContent: 'space-between',
 },
 metricItem: {
 flex: 1,
 alignItems: 'center',
 },
 metricLabel: {
 color: '#94a3b8',
 fontSize: 11,
 textTransform: 'uppercase',
 letterSpacing: 0.5,
 marginBottom: 2,
 },
 metricVal: {
 color: '#f1f5f9',
 fontSize: 13,
 fontWeight: '700',
 },
 bodyScroll: {
 paddingHorizontal: 20,
 },
 bodyContent: {
 paddingVertical: 16,
 },
 reportText: {
 color: '#e2e8f0',
 fontSize: 13,
 lineHeight: 22,
 fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace',
 },
 fallbackContainer: {
 gap: 12,
 },
 sectionHeader: {
 color: '#38bdf8',
 fontSize: 13,
 fontWeight: '700',
 letterSpacing: 0.5,
 marginTop: 8,
 },
 paragraph: {
 color: '#cbd5e1',
 fontSize: 13,
 lineHeight: 20,
 },
 footer: {
 flexDirection: 'row',
 padding: 16,
 backgroundColor: '#1e293b',
 borderTopWidth: 1,
 borderTopColor: '#334155',
 gap: 12,
 },
 downloadBtn: {
 flex: 1,
 flexDirection: 'row',
 alignItems: 'center',
 justifyContent: 'center',
 backgroundColor: '#0284c7',
 paddingVertical: 12,
 borderRadius: 10,
 gap: 8,
 },
 downloadBtnText: {
 color: '#ffffff',
 fontSize: 14,
 fontWeight: '700',
 },
 secondaryBtn: {
 paddingHorizontal: 20,
 justifyContent: 'center',
 alignItems: 'center',
 backgroundColor: '#334155',
 borderRadius: 10,
 },
 secondaryBtnText: {
 color: '#cbd5e1',
 fontSize: 14,
 fontWeight: '600',
 },
});
