import { createStaticNavigation } from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import AnalyzeScreen from './src/screens/AnalyzeScreen';
import HomeScreen from './src/screens/HomeScreen';
import LoadingScreen from './src/screens/LoadingScreen';
import React from 'react';

const RootStack = createNativeStackNavigator({
  initialRouteName: 'Loading',
  screens: {
    Loading: {
      screen: LoadingScreen,
      options: { headerShown: false }
    },
    Home: {
      screen: HomeScreen,
      options: { headerShown: false }
    },
    Analyze: {
      screen: AnalyzeScreen,
      options: { headerShown: false }
    }
  },
});

const Navigation = createStaticNavigation(RootStack);

const App = () => {
  return <Navigation />;
};

export default App;