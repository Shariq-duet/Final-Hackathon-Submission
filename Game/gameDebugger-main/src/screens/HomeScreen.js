import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ImageBackground,
  Pressable,
  Animated,
  Dimensions,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';

const { width } = Dimensions.get('window');

const HomeScreen = () => {
  const navigation = useNavigation();
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const floatAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Pulse animation for the button
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, {
          toValue: 1.05,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(pulseAnim, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    ).start();

    // Float animation for the logo/title
    Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, {
          toValue: -10,
          duration: 1500,
          useNativeDriver: true,
        }),
        Animated.timing(floatAnim, {
          toValue: 0,
          duration: 1500,
          useNativeDriver: true,
        }),
      ])
    ).start();
  }, []);

  return (
    <ImageBackground
      source={require('../assets/bg.png')}
      style={styles.background}
    >
      <View style={styles.overlay}>
        
        {/* Header Section */}
        <Animated.View style={[styles.headerContainer, { transform: [{ translateY: floatAnim }] }]}>
          <Text style={styles.title}>NEXUS</Text>
          <Text style={styles.subtitle}>AI DEBUGGER PROTOCOL</Text>
        </Animated.View>

        {/* Stats Grid */}
        <View style={styles.statsContainer}>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>100%</Text>
            <Text style={styles.statLabel}>SYSTEM UPTIME</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>3</Text>
            <Text style={styles.statLabel}>ACTIVE AGENTS</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>0ms</Text>
            <Text style={styles.statLabel}>LATENCY</Text>
          </View>
          <View style={styles.statBox}>
            <Text style={styles.statValue}>SECURE</Text>
            <Text style={styles.statLabel}>CONNECTION</Text>
          </View>
        </View>

        {/* Main Action */}
        <View style={styles.actionContainer}>
          <Animated.View style={{ transform: [{ scale: pulseAnim }] }}>
            <Pressable
              style={({ pressed }) => [
                styles.button,
                pressed && styles.buttonPressed
              ]}
              onPress={() => navigation.navigate('Analyze')}
            >
              <Text style={styles.buttonText}>INITIALIZE SCAN</Text>
            </Pressable>
          </Animated.View>
        </View>

      </View>
    </ImageBackground>
  );
};

const styles = StyleSheet.create({
  background: {
    flex: 1,
    width: '100%',
    height: '100%',
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(9, 10, 15, 0.65)',
    paddingHorizontal: 20,
    justifyContent: 'space-between',
  },
  headerContainer: {
    marginTop: 80,
    alignItems: 'center',
  },
  title: {
    fontSize: 54,
    fontWeight: '900',
    color: '#00ffff',
    letterSpacing: 8,
    textShadowColor: 'rgba(0, 255, 255, 0.7)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 20,
  },
  subtitle: {
    fontSize: 14,
    color: '#a0aec0',
    letterSpacing: 4,
    marginTop: 10,
    fontWeight: '600',
  },
  statsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: 15,
    marginTop: 40,
  },
  statBox: {
    width: (width - 55) / 2, // 2 columns with gaps
    backgroundColor: 'rgba(20, 25, 35, 0.7)',
    borderRadius: 12,
    padding: 20,
    borderWidth: 1,
    borderColor: 'rgba(0, 255, 255, 0.2)',
    alignItems: 'center',
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 5,
  },
  statLabel: {
    fontSize: 10,
    color: '#00ffff',
    letterSpacing: 2,
    fontWeight: '600',
  },
  actionContainer: {
    marginBottom: 60,
    alignItems: 'center',
  },
  button: {
    backgroundColor: 'rgba(0, 255, 255, 0.1)',
    paddingVertical: 18,
    paddingHorizontal: 40,
    borderRadius: 30,
    borderWidth: 2,
    borderColor: '#00ffff',
    shadowColor: '#00ffff',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 15,
    elevation: 10,
  },
  buttonPressed: {
    backgroundColor: 'rgba(0, 255, 255, 0.3)',
  },
  buttonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
    letterSpacing: 3,
    textShadowColor: '#00ffff',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 10,
  },
});

export default HomeScreen;
