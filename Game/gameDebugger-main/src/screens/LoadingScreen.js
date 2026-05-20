import React, { useEffect, useState, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ImageBackground,
  Animated,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';

const BOOT_SEQUENCE = [
  "[SYSTEM] INITIALIZING KERNEL...",
  "[NETWORK] ESTABLISHING SECURE CONNECTION...",
  "[NEXUS] LOADING AI DEBUGGING MODULES...",
  "[NEXUS] BYPASSING MAINFRAME FIREWALLS...",
  "[SYSTEM] ALL SYSTEMS NOMINAL.",
  "[SYSTEM] LAUNCHING PROTOCOL..."
];

const LoadingScreen = () => {
  const navigation = useNavigation();
  const [loadingText, setLoadingText] = useState(BOOT_SEQUENCE[0]);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const spinnerAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Fade in text
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 800,
      useNativeDriver: true,
    }).start();

    // Spinner rotation
    Animated.loop(
      Animated.timing(spinnerAnim, {
        toValue: 1,
        duration: 2000,
        useNativeDriver: true,
      })
    ).start();

    // Sequence the text updates
    let step = 0;
    const interval = setInterval(() => {
      step++;
      if (step < BOOT_SEQUENCE.length) {
        setLoadingText(BOOT_SEQUENCE[step]);
      } else {
        clearInterval(interval);
        // Navigate to Home when done
        setTimeout(() => {
          navigation.replace('Home');
        }, 500);
      }
    }, 700);

    return () => clearInterval(interval);
  }, []);

  const spin = spinnerAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg']
  });

  return (
    <ImageBackground
      source={require('../assets/bg.png')}
      style={styles.background}
    >
      <View style={styles.overlay}>
        
        <View style={styles.centerContainer}>
          <Animated.View style={[styles.spinner, { transform: [{ rotate: spin }] }]}>
            <View style={styles.spinnerInner} />
          </Animated.View>
          <Text style={styles.title}>NEXUS</Text>
        </View>

        <Animated.View style={[styles.terminalContainer, { opacity: fadeAnim }]}>
          <Text style={styles.terminalText}>{loadingText}</Text>
          <View style={styles.cursor} />
        </Animated.View>

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
    backgroundColor: 'rgba(9, 10, 15, 0.85)', // Darker overlay for loading
    justifyContent: 'center',
    alignItems: 'center',
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    width: 200,
    height: 200,
  },
  spinner: {
    width: 140,
    height: 140,
    borderRadius: 70,
    borderWidth: 3,
    borderColor: 'rgba(0, 255, 255, 0.1)',
    borderTopColor: '#00ffff',
    borderBottomColor: '#00ffff',
    justifyContent: 'center',
    alignItems: 'center',
    position: 'absolute',
  },
  spinnerInner: {
    width: 110,
    height: 110,
    borderRadius: 55,
    borderWidth: 2,
    borderColor: 'rgba(0, 255, 255, 0.05)',
    borderLeftColor: '#00ffff',
    borderRightColor: '#00ffff',
  },
  title: {
    fontSize: 28,
    fontWeight: '900',
    color: '#00ffff',
    letterSpacing: 8,
    textShadowColor: 'rgba(0, 255, 255, 0.8)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 15,
  },
  terminalContainer: {
    position: 'absolute',
    bottom: 50,
    left: 30,
    right: 30,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0, 20, 20, 0.5)',
    padding: 15,
    borderRadius: 5,
    borderLeftWidth: 3,
    borderLeftColor: '#00ffff',
  },
  terminalText: {
    color: '#00ffff',
    fontFamily: 'monospace',
    fontSize: 11,
    letterSpacing: 1,
  },
  cursor: {
    width: 8,
    height: 15,
    backgroundColor: '#00ffff',
    marginLeft: 5,
  }
});

export default LoadingScreen;
