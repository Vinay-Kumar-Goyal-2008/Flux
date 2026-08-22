import React, { useState } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, TextInput, Switch, Alert } from 'react-native';
import { Settings, Server, Shield, Check } from 'lucide-react-native';
import { apiService } from '../services/api';

export const SettingsPanel: React.FC = () => {
  const [useMock, setUseMock] = useState<boolean>(apiService.useMock);
  const [apiUrl, setApiUrl] = useState<string>(apiService.apiUrl);
  const [saved, setSaved] = useState<boolean>(false);

  React.useEffect(() => {
    setUseMock(apiService.useMock);
    setApiUrl(apiService.apiUrl);
  }, []);

  const handleSave = async () => {
    await apiService.setUseMock(useMock);
    await apiService.setApiUrl(apiUrl);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
    Alert.alert('Configuration Saved', `Local Mock mode is now: ${useMock ? 'ON' : 'OFF'}\nAPI Endpoint: ${apiUrl}`);
  };

  return (
    <View style={styles.container}>
      <View style={styles.card}>
        <View style={styles.header}>
          <Settings size={22} color="#2563eb" />
          <Text style={styles.title}>System Settings</Text>
        </View>
        <Text style={styles.subtitle}>
          Configure endpoint routes, toggle demo data feeds, or set local simulation parameters.
        </Text>

        {/* Toggle Switch */}
        <View style={styles.row}>
          <View style={styles.textCol}>
            <Text style={styles.label}>Offline Mock Simulation API</Text>
            <Text style={styles.description}>
              When enabled, the app functions offline using mock data stubs, bypassing the FastAPI server.
            </Text>
          </View>
          <Switch
            value={useMock}
            onValueChange={setUseMock}
            trackColor={{ false: '#cbd5e1', true: '#10b981' }}
            thumbColor={useMock ? '#ffffff' : '#94a3b8'}
          />
        </View>

        {/* API Endpoint Input */}
        <Text style={styles.label}>Server Base API Endpoint URL</Text>
        <View style={styles.inputContainer}>
          <Server size={16} color="#64748b" style={{ marginRight: 8 }} />
          <TextInput
            style={styles.input}
            value={apiUrl}
            onChangeText={setApiUrl}
            placeholder="http://localhost:8000/api"
            placeholderTextColor="#94a3b8"
            editable={!useMock}
          />
        </View>
        {useMock && (
          <Text style={styles.warningText}>
            Note: Disable Offline Mock Simulation to modify the server endpoint.
          </Text>
        )}

        {/* Action Button */}
        {saved ? (
          <View style={styles.successButton}>
            <Check size={16} color="#065f46" style={{ marginRight: 6 }} />
            <Text style={styles.successButtonText}>Saved Settings</Text>
          </View>
        ) : (
          <TouchableOpacity style={styles.saveButton} onPress={handleSave}>
            <Shield size={16} color="#ffffff" style={{ marginRight: 6 }} />
            <Text style={styles.saveButtonText}>Apply Configurations</Text>
          </TouchableOpacity>
        )}
      </View>
      
      {/* Dev Info Footer */}
      <View style={styles.footer}>
        <Text style={styles.footerText}>Floor Rescuer System v1.0.0</Text>
        <Text style={styles.footerSubText}>Model: SegFormer MiT-B2 Gated Fusion</Text>
      </View>
    </View>
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
    marginBottom: 20,
    lineHeight: 16
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#f1f5f9',
    paddingBottom: 16,
    marginBottom: 16
  },
  textCol: {
    flex: 1,
    paddingRight: 16
  },
  label: {
    color: '#334155',
    fontSize: 12,
    fontWeight: 'bold',
    marginBottom: 4
  },
  description: {
    color: '#64748b',
    fontSize: 10,
    lineHeight: 13
  },
  inputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingHorizontal: 12,
    height: 40,
    marginTop: 8,
    marginBottom: 6
  },
  input: {
    flex: 1,
    color: '#0f172a',
    fontSize: 13,
    height: '100%'
  },
  warningText: {
    color: '#d97706',
    fontSize: 10,
    marginBottom: 16
  },
  saveButton: {
    backgroundColor: '#2563eb',
    borderRadius: 8,
    height: 40,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 10
  },
  saveButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: 'bold'
  },
  successButton: {
    backgroundColor: '#d1fae5',
    borderRadius: 8,
    height: 40,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 10,
    borderWidth: 1,
    borderColor: '#10b981'
  },
  successButtonText: {
    color: '#065f46',
    fontSize: 13,
    fontWeight: 'bold'
  },
  footer: {
    marginTop: 40,
    alignItems: 'center'
  },
  footerText: {
    color: '#64748b',
    fontSize: 11
  },
  footerSubText: {
    color: '#94a3b8',
    fontSize: 9,
    marginTop: 2
  }
});
