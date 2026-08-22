import React, { useState } from 'react';
import { StyleSheet, View, Text, TouchableOpacity, TextInput, ActivityIndicator, Alert, ScrollView, Platform } from 'react-native';
import { AlertCircle, CheckCircle2, Navigation, Send, Check } from 'lucide-react-native';
import * as Location from 'expo-location';
import { apiService } from '../services/api';

interface ReportFormProps {
  username: string;
  onReported?: () => void;
}

const CATEGORIES = [
  'Water Logging',
  'Rescue Needed',
  'Medical Emergency',
  'Food/Water Shortage'
];

export const ReportForm: React.FC<ReportFormProps> = ({ username, onReported }) => {
  const [selectedCats, setSelectedCats] = useState<string[]>([]);
  const [placeName, setPlaceName] = useState<string>('');
  const [description, setDescription] = useState<string>('');
  const [severity, setSeverity] = useState<string>('MODERATE');
  const [lat, setLat] = useState<string>('');
  const [lon, setLon] = useState<string>('');
  const [fetchingLocation, setFetchingLocation] = useState<boolean>(false);
  const [geocodingPlace, setGeocodingPlace] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [success, setSuccess] = useState<boolean>(false);

  const handleLookupPlace = async () => {
    const query = placeName.trim();
    if (!query) {
      const msg = 'Please type a place or landmark name to search.';
      if (Platform.OS === 'web') window.alert(msg);
      else Alert.alert('Validation Error', msg);
      return;
    }
    setGeocodingPlace(true);
    try {
      const res = await apiService.geocodePlace(query);
      if (res.status === 'SUCCESS' && typeof res.lat === 'number' && typeof res.lon === 'number') {
        setLat(res.lat.toFixed(6));
        setLon(res.lon.toFixed(6));
        setPlaceName(res.name || query);
      } else {
        const notFoundMsg = `Location "${query}" does not exist. Please check the spelling or enter coordinates manually.`;
        if (Platform.OS === 'web') window.alert(notFoundMsg);
        else Alert.alert('Location Not Found', notFoundMsg);
      }
    } catch (e) {
      console.log('Place lookup error:', e);
      const errMsg = `Location "${query}" does not exist. Please check the spelling or enter coordinates manually.`;
      if (Platform.OS === 'web') window.alert(errMsg);
      else Alert.alert('Search Error', errMsg);
    } finally {
      setGeocodingPlace(false);
    }
  };

  const captureGPS = async () => {
    setFetchingLocation(true);
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission Denied', 'Allow location permission to capture coordinates.');
        return;
      }
      const loc = await Location.getCurrentPositionAsync({});
      const capturedLat = loc.coords.latitude;
      const capturedLon = loc.coords.longitude;
      setLat(capturedLat.toFixed(6));
      setLon(capturedLon.toFixed(6));

      // Reverse geocode to get human place name
      const name = await apiService.reverseGeocode(capturedLat, capturedLon);
      setPlaceName(name || "My Current Location");
    } catch (e) {
      console.log("Location fetch error: ", e);
      Alert.alert('Error', 'Unable to capture native GPS. Please input coordinates manually.');
    } finally {
      setFetchingLocation(false);
    }
  };

  const toggleCategory = (cat: string) => {
    if (selectedCats.includes(cat)) {
      setSelectedCats(prev => prev.filter(c => c !== cat));
    } else {
      setSelectedCats(prev => [...prev, cat]);
    }
  };

  const handleSubmit = async () => {
    const latNum = parseFloat(lat);
    const lonNum = parseFloat(lon);

    if (isNaN(latNum) || isNaN(lonNum)) {
      Alert.alert('Validation Error', 'Please search for a place or supply valid latitude and longitude coordinates.');
      return;
    }
    
    if (selectedCats.length === 0 && !description.trim()) {
      Alert.alert('Validation Error', 'Please select at least one report category or describe the conditions.');
      return;
    }

    setSubmitting(true);
    
    // Combine categories and raw text description
    const formattedDesc = selectedCats.length > 0 
      ? `[Categories: ${selectedCats.join(', ')}] ${description.trim()}`
      : description.trim();

    try {
      const activeUser = (username && username.trim()) ? username.trim() : "citizen_reporter";
      const res = await apiService.submitReport(activeUser, latNum, lonNum, severity, formattedDesc, placeName.trim());
      if (res && (res.status === "SUCCESS" || res.status === "success" || res.id)) {
        setSuccess(true);
        setDescription('');
        setPlaceName('');
        setLat('');
        setLon('');
        setSelectedCats([]);
        if (onReported) onReported();
        
        const successMsg = 'Report Submitted Successfully!\nYour ground condition report has been logged and dispatched to government disaster response officials in real-time.';
        if (Platform.OS === 'web') {
          window.alert(successMsg);
        } else {
          Alert.alert('Report Submitted Successfully', successMsg);
        }
        setTimeout(() => setSuccess(false), 5000);
      } else {
        const errMsg = res?.message || 'Unable to log report. Please try again.';
        if (Platform.OS === 'web') window.alert(errMsg);
        else Alert.alert('Submission Error', errMsg);
      }
    } catch (e: any) {
      console.log('Submit report error: ', e);
      const netMsg = 'Unable to dispatch report. Please check your connection.';
      if (Platform.OS === 'web') window.alert(netMsg);
      else Alert.alert('Error', netMsg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{ paddingBottom: 24 }}>
      {/* Real-Time Success Banner */}
      {success && (
        <View style={{ backgroundColor: '#dcfce7', borderWidth: 1, borderColor: '#86efac', borderRadius: 12, padding: 14, marginBottom: 16, flexDirection: 'row', alignItems: 'center' }}>
          <CheckCircle2 size={22} color="#16a34a" style={{ marginRight: 10 }} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: '#14532d', fontSize: 13, fontWeight: 'bold' }}>Report Submitted Successfully!</Text>
            <Text style={{ color: '#166534', fontSize: 11, marginTop: 2 }}>Your incident report has been registered and dispatched to government disaster officials in real-time.</Text>
          </View>
        </View>
      )}

      <View style={styles.card}>
        <View style={styles.header}>
          <AlertCircle size={20} color="#2563eb" />
          <Text style={styles.title}>Submit Ground Report</Text>
        </View>
        <Text style={styles.subtitle}>
          Help alert nearby community members and government officials by reporting real-time water conditions.
        </Text>

        {/* Place / Landmark Name input with Geocode button */}
        <Text style={styles.label}>Place or Landmark Name</Text>
        <View style={styles.placeSearchRow}>
          <TextInput
            style={[styles.input, { flex: 1, marginBottom: 0, marginRight: 8 }]}
            placeholder="e.g. Gandhi Ghat, Patna or Majuli Island"
            placeholderTextColor="#94a3b8"
            value={placeName}
            onChangeText={setPlaceName}
            onSubmitEditing={handleLookupPlace}
          />
          <TouchableOpacity 
            style={styles.findPlaceBtn} 
            onPress={handleLookupPlace} 
            disabled={geocodingPlace}
          >
            {geocodingPlace ? (
              <ActivityIndicator size="small" color="#ffffff" />
            ) : (
              <Text style={styles.findPlaceBtnText}>Find Coords</Text>
            )}
          </TouchableOpacity>
        </View>

        {/* Fetch GPS button */}
        <TouchableOpacity style={styles.gpsButton} onPress={captureGPS} disabled={fetchingLocation}>
          {fetchingLocation ? (
            <ActivityIndicator size="small" color="#ffffff" />
          ) : (
            <>
              <Navigation size={15} color="#ffffff" style={{ marginRight: 6 }} />
              <Text style={styles.gpsButtonText}>Auto Capture My GPS & Place</Text>
            </>
          )}
        </TouchableOpacity>

        {/* Coordinate Ingestion */}
        <View style={styles.row}>
          <View style={styles.coordCol}>
            <Text style={styles.labelSmall}>Latitude</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. 25.6124"
              placeholderTextColor="#94a3b8"
              keyboardType="numeric"
              value={lat}
              onChangeText={setLat}
            />
          </View>
          <View style={styles.coordCol}>
            <Text style={styles.labelSmall}>Longitude</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. 85.1376"
              placeholderTextColor="#94a3b8"
              keyboardType="numeric"
              value={lon}
              onChangeText={setLon}
            />
          </View>
        </View>

        {/* Categories Options Checklist */}
        <Text style={styles.label}>Report Category Options</Text>
        <View style={styles.optionsContainer}>
          {CATEGORIES.map(cat => {
            const active = selectedCats.includes(cat);
            return (
              <TouchableOpacity
                key={cat}
                style={[styles.optionPill, active && styles.optionPillActive]}
                onPress={() => toggleCategory(cat)}
              >
                <View style={[styles.checkboxCircle, active && styles.checkboxActive]}>
                  {active && <Check size={10} color="#ffffff" />}
                </View>
                <Text style={[styles.optionText, active && styles.optionTextActive]}>{cat}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Severity Selector */}
        <Text style={styles.label}>Observed Severity</Text>
        <View style={styles.severityRow}>
          {['MINOR', 'MODERATE', 'SEVERE'].map((sev) => (
            <TouchableOpacity
              key={sev}
              style={[
                styles.severityOption,
                severity === sev && {
                  backgroundColor: 
                    sev === 'MINOR' ? '#eab308' :
                    sev === 'MODERATE' ? '#f97316' : '#ef4444',
                  borderColor: 
                    sev === 'MINOR' ? '#eab308' :
                    sev === 'MODERATE' ? '#f97316' : '#ef4444'
                }
              ]}
              onPress={() => setSeverity(sev)}
            >
              <Text style={[styles.severityText, severity === sev && { color: '#ffffff', fontWeight: 'bold' }]}>
                {sev}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Description input */}
        <Text style={styles.label}>Additional Details (Optional)</Text>
        <TextInput
          style={[styles.input, styles.textArea]}
          placeholder="Describe water depth, road blockages, or rescue needs..."
          placeholderTextColor="#94a3b8"
          multiline
          numberOfLines={4}
          value={description}
          onChangeText={setDescription}
        />

        {/* Actions */}
        {success ? (
          <View style={styles.successBox}>
            <CheckCircle2 size={16} color="#065f46" style={{ marginRight: 6 }} />
            <Text style={styles.successText}>Report submitted. Alerts triggered locally!</Text>
          </View>
        ) : (
          <TouchableOpacity style={styles.submitButton} onPress={handleSubmit} disabled={submitting}>
            {submitting ? (
              <ActivityIndicator size="small" color="#ffffff" />
            ) : (
              <>
                <Send size={15} color="#ffffff" style={{ marginRight: 6 }} />
                <Text style={styles.submitButtonText}>Broadcast Alert Report</Text>
              </>
            )}
          </TouchableOpacity>
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
    fontSize: 14,
    fontWeight: 'bold',
    marginLeft: 8
  },
  subtitle: {
    color: '#64748b',
    fontSize: 11,
    marginBottom: 16,
    lineHeight: 15
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12
  },
  coordCol: {
    width: '48%'
  },
  label: {
    color: '#334155',
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 8,
    marginTop: 4
  },
  labelSmall: {
    color: '#64748b',
    fontSize: 10,
    fontWeight: '600',
    marginBottom: 4
  },
  placeSearchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12
  },
  findPlaceBtn: {
    backgroundColor: '#0284c7',
    borderRadius: 8,
    height: 40,
    paddingHorizontal: 14,
    justifyContent: 'center',
    alignItems: 'center'
  },
  findPlaceBtnText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: '700'
  },
  input: {
    backgroundColor: '#ffffff',
    color: '#0f172a',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    paddingHorizontal: 12,
    height: 40,
    fontSize: 13
  },
  textArea: {
    height: 70,
    textAlignVertical: 'top',
    paddingVertical: 8,
    marginBottom: 16
  },
  gpsButton: {
    backgroundColor: '#2563eb',
    borderRadius: 8,
    height: 38,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16
  },
  gpsButtonText: {
    color: '#ffffff',
    fontSize: 12,
    fontWeight: 'bold'
  },
  optionsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginBottom: 16
  },
  optionPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f8fafc',
    borderWidth: 1,
    borderColor: '#e2e8f0',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    width: '48%',
    marginBottom: 8
  },
  optionPillActive: {
    backgroundColor: '#e0f2fe',
    borderColor: '#bae6fd'
  },
  checkboxCircle: {
    width: 16,
    height: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
    backgroundColor: '#ffffff'
  },
  checkboxActive: {
    backgroundColor: '#0284c7',
    borderColor: '#0284c7'
  },
  optionText: {
    color: '#475569',
    fontSize: 10,
    fontWeight: '600'
  },
  optionTextActive: {
    color: '#0369a1',
    fontWeight: '700'
  },
  severityRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 16
  },
  severityOption: {
    backgroundColor: '#ffffff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#cbd5e1',
    height: 36,
    width: '30%',
    justifyContent: 'center',
    alignItems: 'center'
  },
  severityText: {
    color: '#64748b',
    fontSize: 11
  },
  submitButton: {
    backgroundColor: '#10b981',
    borderRadius: 8,
    height: 40,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center'
  },
  submitButtonText: {
    color: '#ffffff',
    fontSize: 13,
    fontWeight: 'bold'
  },
  successBox: {
    backgroundColor: '#d1fae5',
    borderRadius: 8,
    height: 40,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#10b981'
  },
  successText: {
    color: '#065f46',
    fontSize: 12,
    fontWeight: 'bold'
  }
});
