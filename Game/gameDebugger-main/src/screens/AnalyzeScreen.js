import React, { useState, useEffect, useRef } from 'react';
import {
    ImageBackground,
    Pressable,
    Text,
    View,
    Alert,
    ScrollView,
    Animated,
    StyleSheet,
    ActivityIndicator,
    Dimensions,
} from "react-native";
import { pick, types } from '@react-native-documents/picker';
import { EXECUTE_URL, ANALYZE_LOCAL_URL, ANALYZE_DEMO_URL, ANALYZE_DISCORD_URL, RESULT_URL, STREAM_URL } from "../config/api";

const { width } = Dimensions.get('window');

const AnalyzeScreen = () => {
    // Pipeline States
    const [jobId, setJobId] = useState(null);
    const [status, setStatus] = useState('IDLE'); // IDLE, RUNNING, COMPLETE, FAILED
    const [phase, setPhase] = useState('STARTING'); // INGEST, CLUSTER, PLAN, COMPLETE
    const [telemetryLogs, setTelemetryLogs] = useState([]);
    const [metrics, setMetrics] = useState({
        logs: '0',
        bugs: '0',
        time: '00:00'
    });
    const [executionPlan, setExecutionPlan] = useState(null);
    const [rawPlan, setRawPlan] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [expandedIncidents, setExpandedIncidents] = useState({});
    const [uploadedFile, setUploadedFile] = useState(null);
    const [approvalStatus, setApprovalStatus] = useState('pending'); // pending, executing, success, failed

    // UI Clock
    const [currentTime, setCurrentTime] = useState('');
    
    // Animations & Refs
    const sseXhrRef = useRef(null);
    const timerIntervalRef = useRef(null);
    const pipelineStartRef = useRef(null);
    const scrollViewRef = useRef(null);
    const pulseAnim = useRef(new Animated.Value(1)).current;

    useEffect(() => {
        // System clock
        const tick = () => {
            const now = new Date();
            const hrs = String(now.getHours()).padStart(2, '0');
            const mins = String(now.getMinutes()).padStart(2, '0');
            const secs = String(now.getSeconds()).padStart(2, '0');
            setCurrentTime(`${hrs}:${mins}:${secs}`);
        };
        tick();
        const clockInterval = setInterval(tick, 1000);

        // Pulse animation for active phase indicator
        Animated.loop(
            Animated.sequence([
                Animated.timing(pulseAnim, {
                    toValue: 1.2,
                    duration: 1000,
                    useNativeDriver: true,
                }),
                Animated.timing(pulseAnim, {
                    toValue: 1,
                    duration: 1000,
                    useNativeDriver: true,
                })
            ])
        ).start();

        return () => {
            clearInterval(clockInterval);
            stopTimer();
            if (sseXhrRef.current) sseXhrRef.current.abort();
        };
    }, []);

    // Timer helpers
    const startTimer = () => {
        if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
        pipelineStartRef.current = Date.now();
        timerIntervalRef.current = setInterval(() => {
            const elapsed = Math.floor((Date.now() - pipelineStartRef.current) / 1000);
            const mins = String(Math.floor(elapsed / 60)).padStart(2, '0');
            const secs = String(elapsed % 60).padStart(2, '0');
            setMetrics(prev => ({ ...prev, time: `${mins}:${secs}` }));
        }, 1000);
    };

    const stopTimer = () => {
        if (timerIntervalRef.current) {
            clearInterval(timerIntervalRef.current);
            timerIntervalRef.current = null;
        }
    };

    // Telemetry SSE Client
    const connectSSE = (id) => {
        if (sseXhrRef.current) {
            sseXhrRef.current.abort();
        }

        setTelemetryLogs([]);
        setExecutionPlan(null);
        setRawPlan(null);
        setApprovalStatus('pending');
        setStatus('RUNNING');
        setPhase('INGEST');
        setMetrics({ logs: '0', bugs: '0', time: '00:00' });
        startTimer();

        const xhr = new XMLHttpRequest();
        sseXhrRef.current = xhr;
        xhr.open('GET', STREAM_URL(id));
        xhr.setRequestHeader('Accept', 'text/event-stream');

        let seenBytes = 0;
        let currentEvent = null;
        let buffer = '';

        xhr.onreadystatechange = () => {
            if (xhr.readyState === 3 || xhr.readyState === 4) {
                const responseText = xhr.responseText || '';
                const newText = responseText.substring(seenBytes);
                seenBytes = responseText.length;

                buffer += newText;
                const lines = buffer.split('\n');
                buffer = lines.pop();

                lines.forEach(line => {
                    const trimmed = line.trim();
                    if (trimmed.startsWith('event:')) {
                        currentEvent = trimmed.substring(6).trim();
                    } else if (trimmed.startsWith('data:')) {
                        const dataStr = trimmed.substring(5).trim();
                        if (currentEvent === 'telemetry') {
                            try {
                                const eventData = JSON.parse(dataStr);
                                handleTelemetryEvent(eventData);
                            } catch (e) {}
                        } else if (currentEvent === 'complete') {
                            try {
                                const plan = JSON.parse(dataStr);
                                handlePipelineComplete(plan);
                                xhr.abort();
                            } catch (e) {}
                        } else if (currentEvent === 'error') {
                            try {
                                const err = JSON.parse(dataStr);
                                handlePipelineFailed(err.error || 'Pipeline failed');
                                xhr.abort();
                            } catch (e) {}
                        }
                    } else if (trimmed === '') {
                        currentEvent = null;
                    }
                });
            }
        };

        xhr.onerror = () => {
            handlePipelineFailed('Stream connection error');
        };

        xhr.send();
    };

    const handleTelemetryEvent = (event) => {
        setTelemetryLogs(prev => [...prev, event]);

        const msg = event.message || '';
        if (msg.includes('PHASE 1')) {
            setPhase('INGEST');
        } else if (msg.includes('PHASE 2')) {
            setPhase('CLUSTER');
        } else if (msg.includes('PHASE 3')) {
            setPhase('PLAN');
        }

        const logsMatch = msg.match(/(\d+)\s+(?:total\s+)?(?:structured\s+)?logs/i);
        if (logsMatch) {
            setMetrics(prev => ({ ...prev, logs: logsMatch[1] }));
        }

        const bugsMatch = msg.match(/(\d+)\s+distinct/i) || msg.match(/isolated\s+(\d+)/i);
        if (bugsMatch) {
            setMetrics(prev => ({ ...prev, bugs: bugsMatch[1] }));
        }
    };

    const handlePipelineComplete = (plan) => {
        stopTimer();
        setStatus('COMPLETE');
        setPhase('COMPLETE');
        setRawPlan(plan);

        const uiPlan = {
            executive_summary: `AI pipeline completed. Generated ${plan.actions?.length || 0} actionable items from community log analysis.`,
            incidents: (plan.actions || []).map(action => ({
                severity: action.severity?.toLowerCase() || 'info',
                description: action.incident_title || 'Unknown Incident',
                recommended_action: action.implication_analysis || 'No analysis available',
                jira_ticket: action.jira_title ? { title: action.jira_title, desc: action.jira_description_markdown } : null,
                code_patch: action.simulated_code_patch || null,
                discord_announcement: action.discord_announcement_markdown || null,
            }))
        };
        setExecutionPlan(uiPlan);
        
        // Expand the first incident card by default
        if (uiPlan.incidents.length > 0) {
            setExpandedIncidents({ 0: true });
        }
        
        Alert.alert("Analysis Complete", `AI found ${uiPlan.incidents.length} incidents.`);
    };

    const handlePipelineFailed = (errorMsg) => {
        stopTimer();
        setStatus('FAILED');
        Alert.alert("Pipeline Failed", errorMsg);
    };

    const handleConsoleContentSizeChange = () => {
        if (scrollViewRef.current) {
            scrollViewRef.current.scrollToEnd({ animated: true });
        }
    };

    // Document Picker & Upload Handlers
    const handlePickFile = async () => {
        try {
            const results = await pick({
                type: [types.plainText || 'text/plain'],
                allowMultiSelection: false,
                mode: 'import'
            });

            if (results && results.length > 0) {
                setUploadedFile(results[0]);
            }
        } catch (err) {
            console.log('File picker error:', err);
        }
    };

    const handleClearFile = () => {
        setUploadedFile(null);
    };

    const handleUploadAndAnalyze = async () => {
        if (!uploadedFile) return;

        setIsLoading(true);
        try {
            const fd = new FormData();
            fd.append('file', {
                uri: uploadedFile.uri,
                type: uploadedFile.type || 'text/plain',
                name: uploadedFile.name || 'logs.txt'
            });

            const uploadUrl = ANALYZE_LOCAL_URL.replace('/analyze-local', '/analyze-upload');
            const response = await fetch(uploadUrl, {
                method: 'POST',
                body: fd,
                headers: {
                    'Content-Type': 'multipart/form-data',
                }
            });

            if (!response.ok) {
                throw new Error(`Upload failed with status ${response.status}`);
            }

            const data = await response.json();
            if (data.job_id) {
                setJobId(data.job_id);
                connectSSE(data.job_id);
            }
        } catch (error) {
            Alert.alert("Upload Error", error.message || "Failed to upload log file.");
        } finally {
            setIsLoading(false);
        }
    };

    // Action Triggers
    const triggerLocalAnalysis = async () => {
        setIsLoading(true);
        try {
            const response = await fetch(ANALYZE_LOCAL_URL, { method: 'POST' });
            if (!response.ok) throw new Error('Failed to trigger local analysis');
            const data = await response.json();
            if (data.job_id) {
                setJobId(data.job_id);
                connectSSE(data.job_id);
            }
        } catch (error) {
            Alert.alert("Error", error.message);
        } finally {
            setIsLoading(false);
        }
    };

    const triggerDiscordAnalysis = async () => {
        setIsLoading(true);
        try {
            const response = await fetch(ANALYZE_DISCORD_URL, { method: 'POST' });
            if (!response.ok) throw new Error('Failed to trigger Discord analysis');
            const data = await response.json();
            if (data.job_id) {
                setJobId(data.job_id);
                connectSSE(data.job_id);
            }
        } catch (error) {
            Alert.alert("Error", error.message);
        } finally {
            setIsLoading(false);
        }
    };

    const triggerDemoAnalysis = async () => {
        setIsLoading(true);
        try {
            const response = await fetch(ANALYZE_DEMO_URL, { method: 'POST' });
            if (!response.ok) throw new Error('Failed to trigger demo analysis');
            const data = await response.json();
            if (data.job_id) {
                setJobId(data.job_id);
                connectSSE(data.job_id);
            }
        } catch (error) {
            Alert.alert("Error", error.message);
        } finally {
            setIsLoading(false);
        }
    };

    const executeApprovedPlan = async () => {
        if (!rawPlan) return;

        setApprovalStatus('executing');
        try {
            const response = await fetch(EXECUTE_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(rawPlan)
            });

            if (!response.ok) {
                throw new Error("Execution request failed");
            }

            setApprovalStatus('success');
            Alert.alert("Success", "Approved fixes executed! Jira tickets created & Discord notified.");
        } catch (error) {
            setApprovalStatus('failed');
            Alert.alert("Error", "Failed to execute approved plan.");
        }
    };

    const resetPipeline = () => {
        if (sseXhrRef.current) sseXhrRef.current.abort();
        stopTimer();
        setStatus('IDLE');
        setPhase('STARTING');
        setJobId(null);
        setTelemetryLogs([]);
        setExecutionPlan(null);
        setRawPlan(null);
        setMetrics({ logs: '0', bugs: '0', time: '00:00' });
    };

    const toggleIncidentExpand = (idx) => {
        setExpandedIncidents(prev => ({
            ...prev,
            [idx]: !prev[idx]
        }));
    };

    // Helper: Style matching for Severity level
    const getSeverityStyles = (severity) => {
        switch (severity?.toLowerCase()) {
            case 'critical':
                return { color: '#ff0055', bg: 'rgba(255, 0, 85, 0.1)', border: '#ff0055' };
            case 'high':
                return { color: '#ff8800', bg: 'rgba(255, 136, 0, 0.1)', border: '#ff8800' };
            case 'medium':
                return { color: '#facc15', bg: 'rgba(250, 204, 21, 0.1)', border: '#facc15' };
            default:
                return { color: '#00ffff', bg: 'rgba(0, 255, 255, 0.1)', border: '#00ffff' };
        }
    };

    // Helper: Get text-color class for log level
    const getLogLevelColor = (type) => {
        switch (type?.toLowerCase()) {
            case 'phase':
                return '#f59e0b';
            case 'action':
                return '#00ffff';
            case 'observation':
                return '#10b981';
            case 'reasoning':
                return '#a855f7';
            case 'error':
                return '#ef4444';
            default:
                return '#e2e8f0';
        }
    };

    return (
        <ImageBackground
            source={require('../assets/bg.png')}
            style={styles.background}
        >
            <View style={styles.overlay}>
                
                {/* HEADER */}
                <View style={styles.header}>
                    <View style={styles.headerTopRow}>
                        <View style={styles.statusWidget}>
                            <View style={styles.statusDot} />
                            <Text style={styles.statusText}>SYS_ON</Text>
                        </View>
                        <Text style={styles.clockText}>{currentTime}</Text>
                    </View>
                    <Text style={styles.title}>GAME DEBUGGER</Text>
                    <Text style={styles.subtitle}>MISSION CONTROL DASHBOARD</Text>
                </View>

                {/* MAIN CONTENT AREA */}
                {status === 'IDLE' ? (
                    // LAUNCH PANEL (IDLE State)
                    <ScrollView style={styles.mainScroll} contentContainerStyle={styles.mainScrollContent}>
                        {isLoading && (
                            <View style={styles.globalLoader}>
                                <ActivityIndicator size="large" color="#00ffff" />
                                <Text style={styles.globalLoaderText}>INITIALIZING PROTOCOL...</Text>
                            </View>
                        )}
                        
                        {/* 1. File Upload zone */}
                        <View style={styles.glassCard}>
                            <Text style={styles.cardHeader}>📁 UPLOAD LOG FILE</Text>
                            
                            {!uploadedFile ? (
                                <Pressable style={styles.dropZone} onPress={handlePickFile}>
                                    <Text style={styles.dropZoneIcon}>📄</Text>
                                    <Text style={styles.dropZoneTitle}>Select server log .txt file</Text>
                                    <Text style={styles.dropZoneSubtitle}>Tap to browse device storage</Text>
                                </Pressable>
                            ) : (
                                <View style={styles.fileSelectedContainer}>
                                    <View style={styles.fileInfo}>
                                        <Text style={styles.fileName}>{uploadedFile.name}</Text>
                                        <Text style={styles.fileSize}>
                                            {(uploadedFile.size / 1024).toFixed(1)} KB
                                        </Text>
                                    </View>
                                    <View style={styles.fileActions}>
                                        <Pressable style={styles.clearFileButton} onPress={handleClearFile}>
                                            <Text style={styles.clearFileText}>Clear</Text>
                                        </Pressable>
                                        <Pressable style={styles.uploadSubmitButton} onPress={handleUploadAndAnalyze}>
                                            <Text style={styles.uploadSubmitText}>Upload & Analyze</Text>
                                        </Pressable>
                                    </View>
                                </View>
                            )}
                        </View>

                        {/* 2. Alternative triggers */}
                        <View style={styles.glassCard}>
                            <Text style={styles.cardHeader}>💾 LOCAL ARCHIVE</Text>
                            <Pressable style={styles.cyberButton} onPress={triggerLocalAnalysis}>
                                <Text style={styles.cyberButtonText}>▶ RUN LOCAL LOG ANALYSIS</Text>
                            </Pressable>
                        </View>

                        <View style={styles.glassCard}>
                            <Text style={styles.cardHeader}>🔴 LIVE CONNECTORS</Text>
                            <Pressable style={[styles.cyberButton, styles.discordButton]} onPress={triggerDiscordAnalysis}>
                                <Text style={styles.cyberButtonText}>⚡ FETCH & ANALYZE DISCORD</Text>
                            </Pressable>
                        </View>

                        <View style={[styles.glassCard, styles.demoCard]}>
                            <Text style={styles.cardHeader}>🎭 MOCK SIMULATOR</Text>
                            <Pressable style={styles.demoButton} onPress={triggerDemoAnalysis}>
                                <Text style={styles.demoButtonText}>🎬 RUN DEMO PIPELINE</Text>
                            </Pressable>
                        </View>
                    </ScrollView>
                ) : (
                    // ACTIVE MISSION VIEW (RUNNING, COMPLETE, FAILED)
                    <View style={styles.missionContainer}>
                        {/* Control header to go back */}
                        <View style={styles.missionHeader}>
                            <Pressable style={styles.resetButton} onPress={resetPipeline}>
                                <Text style={styles.resetButtonText}>◀ RESET PIPELINE</Text>
                            </Pressable>
                            <View style={styles.jobIdBadge}>
                                <Text style={styles.jobIdText}>JOB: {jobId ? jobId.toUpperCase() : '...'}</Text>
                            </View>
                        </View>

                        {/* Phase Progress Bar */}
                        <View style={styles.phaseBar}>
                            <View style={styles.phaseStep}>
                                <View style={[
                                    styles.phaseDot,
                                    (phase === 'INGEST' || phase === 'CLUSTER' || phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseDotActive,
                                    (phase === 'CLUSTER' || phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseDotCompleted
                                ]}>
                                    {phase === 'INGEST' && (
                                        <Animated.View style={[styles.phaseDotPulse, { transform: [{ scale: pulseAnim }] }]} />
                                    )}
                                    <Text style={styles.phaseNumber}>1</Text>
                                </View>
                                <Text style={[
                                    styles.phaseLabel,
                                    (phase === 'INGEST' || phase === 'CLUSTER' || phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseLabelActive
                                ]}>Ingest</Text>
                            </View>

                            <View style={[
                                styles.phaseLine,
                                (phase === 'CLUSTER' || phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseLineActive
                            ]} />

                            <View style={styles.phaseStep}>
                                <View style={[
                                    styles.phaseDot,
                                    (phase === 'CLUSTER' || phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseDotActive,
                                    (phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseDotCompleted
                                ]}>
                                    {phase === 'CLUSTER' && (
                                        <Animated.View style={[styles.phaseDotPulse, { transform: [{ scale: pulseAnim }] }]} />
                                    )}
                                    <Text style={styles.phaseNumber}>2</Text>
                                </View>
                                <Text style={[
                                    styles.phaseLabel,
                                    (phase === 'CLUSTER' || phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseLabelActive
                                ]}>Cluster</Text>
                            </View>

                            <View style={[
                                styles.phaseLine,
                                (phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseLineActive
                            ]} />

                            <View style={styles.phaseStep}>
                                <View style={[
                                    styles.phaseDot,
                                    (phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseDotActive,
                                    phase === 'COMPLETE' && styles.phaseDotCompleted
                                ]}>
                                    {phase === 'PLAN' && (
                                        <Animated.View style={[styles.phaseDotPulse, { transform: [{ scale: pulseAnim }] }]} />
                                    )}
                                    <Text style={styles.phaseNumber}>3</Text>
                                </View>
                                <Text style={[
                                    styles.phaseLabel,
                                    (phase === 'PLAN' || phase === 'COMPLETE') && styles.phaseLabelActive
                                ]}>Plan</Text>
                            </View>
                        </View>

                        {/* Metrics Bar */}
                        <View style={styles.metricsRow}>
                            <View style={styles.metricItem}>
                                <Text style={styles.metricLabel}>LOGS INGESTED</Text>
                                <Text style={styles.metricValue}>{metrics.logs}</Text>
                            </View>
                            <View style={styles.metricItem}>
                                <Text style={styles.metricLabel}>BUGS FOUND</Text>
                                <Text style={styles.metricValue}>{metrics.bugs}</Text>
                            </View>
                            <View style={styles.metricItem}>
                                <Text style={styles.metricLabel}>ELAPSED TIME</Text>
                                <Text style={styles.metricValue}>{metrics.time}</Text>
                            </View>
                            <View style={styles.metricItem}>
                                <Text style={styles.metricLabel}>ACTIVE PHASE</Text>
                                <Text style={[styles.metricValue, { color: '#00ffff' }]}>{phase}</Text>
                            </View>
                        </View>

                        {/* Live Telemetry Logger console */}
                        <Text style={styles.consoleTitle}>📡 LIVE TELEMETRY FEED</Text>
                        <View style={styles.consoleContainer}>
                            <ScrollView
                                ref={scrollViewRef}
                                style={styles.consoleScroll}
                                onContentSizeChange={handleConsoleContentSizeChange}
                                contentContainerStyle={{ padding: 12 }}
                            >
                                {telemetryLogs.length === 0 ? (
                                    <Text style={styles.consolePlaceholder}>Connecting and establishing telemetry socket...</Text>
                                ) : (
                                    telemetryLogs.map((log, index) => (
                                        <View key={index} style={styles.logLine}>
                                            <Text style={styles.logTimestamp}>[{log.timestamp}]</Text>
                                            <Text style={[styles.logMessage, { color: getLogLevelColor(log.type) }]}>
                                                {log.message}
                                            </Text>
                                        </View>
                                    ))
                                )}
                            </ScrollView>
                            {status === 'RUNNING' && (
                                <View style={styles.consoleLoader}>
                                    <ActivityIndicator size="small" color="#00ffff" />
                                    <Text style={styles.consoleLoaderText}>POLLING EVENTS...</Text>
                                </View>
                            )}
                        </View>

                        {/* Execution Plan & Approval (if Complete) */}
                        {status === 'COMPLETE' && executionPlan && (
                            <ScrollView style={styles.planScroll} contentContainerStyle={styles.planContentContainer}>
                                <Text style={styles.planSectionHeader}>📋 INCIDENT RESOLUTION PLAN</Text>
                                <Text style={styles.summaryText}>{executionPlan.executive_summary}</Text>

                                {executionPlan.incidents?.map((incident, idx) => {
                                    const expanded = !!expandedIncidents[idx];
                                    const stylesSet = getSeverityStyles(incident.severity);

                                    return (
                                        <View key={idx} style={[styles.incidentCard, { borderColor: stylesSet.border }]}>
                                            {/* Header triggers expand */}
                                            <Pressable
                                                style={styles.incidentHeader}
                                                onPress={() => toggleIncidentExpand(idx)}
                                            >
                                                <View style={styles.incidentHeaderLeft}>
                                                    <View style={[styles.severityBadge, { borderColor: stylesSet.border, backgroundColor: stylesSet.bg }]}>
                                                        <Text style={[styles.severityText, { color: stylesSet.color }]}>
                                                            {incident.severity.toUpperCase()}
                                                        </Text>
                                                    </View>
                                                    <Text style={styles.incidentTitleText} numberOfLines={1}>
                                                        {incident.description}
                                                    </Text>
                                                </View>
                                                <Text style={styles.incidentToggleIcon}>{expanded ? '▲' : '▼'}</Text>
                                            </Pressable>

                                            {/* Expandable details */}
                                            {expanded && (
                                                <View style={styles.incidentDetails}>
                                                    <Text style={styles.detailLabel}>IMPLICATION ANALYSIS</Text>
                                                    <Text style={styles.detailContent}>{incident.recommended_action}</Text>

                                                    {incident.jira_ticket && (
                                                        <View style={styles.jiraSection}>
                                                            <Text style={styles.detailLabel}>JIRA ASSIGNED: {incident.jira_ticket.title}</Text>
                                                            <Text style={styles.detailContent}>{incident.jira_ticket.desc}</Text>
                                                        </View>
                                                    )}

                                                    {incident.discord_announcement && (
                                                        <View style={styles.discordSection}>
                                                            <Text style={styles.detailLabel}>DISCORD PUBLIC WORKAROUND</Text>
                                                            <Text style={styles.detailContent}>{incident.discord_announcement}</Text>
                                                        </View>
                                                    )}

                                                    {incident.code_patch && (
                                                        <View style={styles.codeSection}>
                                                            <Text style={styles.detailLabel}>SIMULATED CODE PATCH</Text>
                                                            <ScrollView horizontal style={styles.codeScrollView}>
                                                                <Text style={styles.codeBlockText}>{incident.code_patch}</Text>
                                                            </ScrollView>
                                                        </View>
                                                    )}
                                                </View>
                                            )}
                                        </View>
                                    );
                                })}
                                
                                <View style={{ height: 100 }} />
                            </ScrollView>
                        )}
                        
                        {/* BOTTOM APPROVAL BAR (complete state only) */}
                        {status === 'COMPLETE' && (
                            <View style={styles.approvalBar}>
                                <View style={styles.approvalInfo}>
                                    <Text style={styles.approvalStatusLabel}>STATUS:</Text>
                                    {approvalStatus === 'pending' && (
                                        <Text style={styles.approvalStatusTextPending}>⚡ PENDING HUMAN APPROVAL</Text>
                                    )}
                                    {approvalStatus === 'executing' && (
                                        <Text style={styles.approvalStatusTextExecuting}>⏳ EXECUTING WEBHOOKS...</Text>
                                    )}
                                    {approvalStatus === 'success' && (
                                        <Text style={styles.approvalStatusTextSuccess}>✅ FIXES APPLIED SUCCESSFULLY</Text>
                                    )}
                                    {approvalStatus === 'failed' && (
                                        <Text style={styles.approvalStatusTextFailed}>❌ EXECUTION REGRESSION</Text>
                                    )}
                                </View>
                                
                                <Pressable
                                    style={[
                                        styles.approveButton,
                                        approvalStatus === 'success' && styles.approveButtonSuccess,
                                        approvalStatus === 'executing' && styles.approveButtonDisabled
                                    ]}
                                    onPress={executeApprovedPlan}
                                    disabled={approvalStatus === 'success' || approvalStatus === 'executing'}
                                >
                                    {approvalStatus === 'executing' ? (
                                        <ActivityIndicator color="#fff" size="small" />
                                    ) : (
                                        <Text style={styles.approveButtonText}>
                                            {approvalStatus === 'success' ? 'MISSION COMPLETE' : 'APPROVE & EXECUTE'}
                                        </Text>
                                    )}
                                </Pressable>
                            </View>
                        )}
                    </View>
                )}

            </View>
        </ImageBackground>
    );
};

const styles = StyleSheet.create({
    background: {
        flex: 1,
        width: '100%',
        height: '100%'
    },
    overlay: {
        flex: 1,
        backgroundColor: 'rgba(10, 14, 26, 0.85)',
        paddingTop: 45,
    },
    header: {
        alignItems: "center",
        marginBottom: 15,
        paddingHorizontal: 20,
    },
    headerTopRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        width: '100%',
        alignItems: 'center',
        marginBottom: 8,
    },
    statusWidget: {
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(0, 255, 255, 0.1)',
        paddingHorizontal: 10,
        paddingVertical: 3,
        borderRadius: 12,
        borderWidth: 1,
        borderColor: 'rgba(0, 255, 255, 0.3)',
    },
    statusDot: {
        width: 6,
        height: 6,
        borderRadius: 3,
        backgroundColor: '#10b981',
        marginRight: 6,
    },
    statusText: {
        fontSize: 10,
        color: '#00ffff',
        fontWeight: 'bold',
        letterSpacing: 1,
    },
    clockText: {
        color: '#a0aec0',
        fontSize: 11,
        fontFamily: 'monospace',
    },
    title: {
        fontSize: 34,
        color: '#00ffff',
        fontWeight: '950',
        letterSpacing: 6,
        textShadowColor: 'rgba(0, 255, 255, 0.8)',
        textShadowOffset: { width: 0, height: 0 },
        textShadowRadius: 15,
    },
    subtitle: {
        fontSize: 10,
        color: '#a0aec0',
        letterSpacing: 3,
        fontWeight: '700',
        marginTop: 4,
    },
    mainScroll: {
        flex: 1,
        paddingHorizontal: 16,
    },
    mainScrollContent: {
        paddingBottom: 40,
    },
    globalLoader: {
        paddingVertical: 20,
        alignItems: 'center',
        justifyContent: 'center',
    },
    globalLoaderText: {
        color: '#00ffff',
        fontSize: 12,
        fontWeight: 'bold',
        letterSpacing: 2,
        marginTop: 10,
    },
    glassCard: {
        backgroundColor: 'rgba(20, 25, 35, 0.7)',
        borderColor: 'rgba(0, 255, 255, 0.15)',
        borderWidth: 1,
        borderRadius: 12,
        padding: 16,
        marginBottom: 16,
        shadowColor: '#00ffff',
        shadowOffset: { width: 0, height: 0 },
        shadowOpacity: 0.1,
        shadowRadius: 10,
    },
    demoCard: {
        borderColor: 'rgba(168, 85, 247, 0.3)',
        shadowColor: '#a855f7',
    },
    cardHeader: {
        fontSize: 12,
        color: '#00ffff',
        fontWeight: 'bold',
        letterSpacing: 2,
        marginBottom: 12,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(0, 255, 255, 0.15)',
        paddingBottom: 5,
    },
    dropZone: {
        borderWidth: 1.5,
        borderColor: 'rgba(0, 255, 255, 0.3)',
        borderStyle: 'dashed',
        borderRadius: 8,
        paddingVertical: 24,
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.3)',
    },
    dropZoneIcon: {
        fontSize: 32,
        marginBottom: 6,
    },
    dropZoneTitle: {
        color: '#fff',
        fontWeight: 'bold',
        fontSize: 14,
        marginBottom: 4,
    },
    dropZoneSubtitle: {
        color: '#a0aec0',
        fontSize: 10,
    },
    fileSelectedContainer: {
        backgroundColor: 'rgba(0, 0, 0, 0.4)',
        padding: 12,
        borderRadius: 8,
        borderWidth: 1,
        borderColor: 'rgba(0, 255, 255, 0.3)',
    },
    fileInfo: {
        marginBottom: 12,
    },
    fileName: {
        color: '#fff',
        fontWeight: 'bold',
        fontSize: 14,
    },
    fileSize: {
        color: '#00ffff',
        fontSize: 11,
        marginTop: 2,
    },
    fileActions: {
        flexDirection: 'row',
        justifyContent: 'flex-end',
        gap: 10,
    },
    clearFileButton: {
        backgroundColor: 'rgba(255, 0, 85, 0.1)',
        borderWidth: 1,
        borderColor: '#ff0055',
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 6,
    },
    clearFileText: {
        color: '#ff0055',
        fontSize: 12,
        fontWeight: 'bold',
    },
    uploadSubmitButton: {
        backgroundColor: 'rgba(16, 185, 129, 0.2)',
        borderWidth: 1,
        borderColor: '#10b981',
        paddingVertical: 8,
        paddingHorizontal: 16,
        borderRadius: 6,
    },
    uploadSubmitText: {
        color: '#10b981',
        fontSize: 12,
        fontWeight: 'bold',
    },
    cyberButton: {
        backgroundColor: 'rgba(0, 255, 255, 0.08)',
        borderColor: '#00ffff',
        borderWidth: 1,
        borderRadius: 8,
        paddingVertical: 14,
        alignItems: 'center',
        justifyContent: 'center',
    },
    cyberButtonText: {
        color: '#fff',
        fontWeight: 'bold',
        fontSize: 12,
        letterSpacing: 2,
    },
    discordButton: {
        backgroundColor: 'rgba(59, 130, 246, 0.08)',
        borderColor: '#3b82f6',
    },
    demoButton: {
        backgroundColor: 'rgba(168, 85, 247, 0.15)',
        borderColor: '#a855f7',
        borderWidth: 1,
        borderRadius: 8,
        paddingVertical: 14,
        alignItems: 'center',
        justifyContent: 'center',
    },
    demoButtonText: {
        color: '#fff',
        fontWeight: 'bold',
        fontSize: 12,
        letterSpacing: 2,
        textShadowColor: '#a855f7',
        textShadowOffset: { width: 0, height: 0 },
        textShadowRadius: 8,
    },

    // MISSION CONTAINER
    missionContainer: {
        flex: 1,
        paddingHorizontal: 16,
    },
    missionHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 12,
    },
    resetButton: {
        backgroundColor: 'rgba(255,255,255,0.05)',
        borderColor: 'rgba(255,255,255,0.2)',
        borderWidth: 1,
        borderRadius: 6,
        paddingVertical: 6,
        paddingHorizontal: 12,
    },
    resetButtonText: {
        color: '#a0aec0',
        fontSize: 10,
        fontWeight: 'bold',
    },
    jobIdBadge: {
        backgroundColor: 'rgba(0, 255, 255, 0.1)',
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: 6,
        borderWidth: 1,
        borderColor: 'rgba(0, 255, 255, 0.2)',
    },
    jobIdText: {
        fontSize: 10,
        fontFamily: 'monospace',
        color: '#00ffff',
        fontWeight: 'bold',
    },

    // PHASE PROGRESS BAR
    phaseBar: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: 'rgba(20, 25, 35, 0.6)',
        borderRadius: 8,
        padding: 12,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.05)',
        marginBottom: 14,
    },
    phaseStep: {
        alignItems: 'center',
        width: 60,
    },
    phaseDot: {
        width: 28,
        height: 28,
        borderRadius: 14,
        backgroundColor: 'rgba(255, 255, 255, 0.1)',
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: 2,
        borderColor: 'rgba(255,255,255,0.2)',
    },
    phaseDotPulse: {
        position: 'absolute',
        width: 32,
        height: 32,
        borderRadius: 16,
        borderWidth: 2,
        borderColor: '#00ffff',
        opacity: 0.8,
    },
    phaseDotActive: {
        borderColor: '#00ffff',
        backgroundColor: 'rgba(0, 255, 255, 0.15)',
    },
    phaseDotCompleted: {
        borderColor: '#10b981',
        backgroundColor: '#10b981',
    },
    phaseNumber: {
        fontSize: 11,
        color: '#fff',
        fontWeight: 'bold',
    },
    phaseLabel: {
        fontSize: 9,
        color: '#a0aec0',
        marginTop: 4,
        fontWeight: 'bold',
        letterSpacing: 1,
    },
    phaseLabelActive: {
        color: '#00ffff',
    },
    phaseLine: {
        flex: 1,
        height: 2,
        backgroundColor: 'rgba(255,255,255,0.1)',
        marginHorizontal: -5,
    },
    phaseLineActive: {
        backgroundColor: '#00ffff',
    },

    // METRICS ROW
    metricsRow: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        gap: 8,
        marginBottom: 14,
    },
    metricItem: {
        flex: 1,
        backgroundColor: 'rgba(20, 25, 35, 0.8)',
        borderRadius: 8,
        padding: 8,
        borderWidth: 1,
        borderColor: 'rgba(0, 255, 255, 0.1)',
        alignItems: 'center',
    },
    metricLabel: {
        fontSize: 7,
        color: '#a0aec0',
        letterSpacing: 1,
        fontWeight: 'bold',
        marginBottom: 3,
    },
    metricValue: {
        fontSize: 12,
        fontWeight: 'bold',
        color: '#fff',
    },

    // CONSOLE TERMINAL
    consoleTitle: {
        fontSize: 10,
        color: '#00ffff',
        fontWeight: 'bold',
        letterSpacing: 1.5,
        marginBottom: 6,
    },
    consoleContainer: {
        height: 180,
        backgroundColor: 'rgba(0, 5, 10, 0.95)',
        borderRadius: 8,
        borderWidth: 1.5,
        borderColor: 'rgba(0, 255, 255, 0.3)',
        marginBottom: 14,
    },
    consoleScroll: {
        flex: 1,
    },
    consolePlaceholder: {
        color: '#a0aec0',
        fontSize: 11,
        fontFamily: 'monospace',
        textAlign: 'center',
        marginTop: 60,
    },
    logLine: {
        flexDirection: 'row',
        marginBottom: 4,
    },
    logTimestamp: {
        color: '#a0aec0',
        fontFamily: 'monospace',
        fontSize: 10,
        marginRight: 6,
    },
    logMessage: {
        flex: 1,
        fontFamily: 'monospace',
        fontSize: 10.5,
        lineHeight: 14,
    },
    consoleLoader: {
        position: 'absolute',
        bottom: 8,
        right: 12,
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: 'rgba(0,0,0,0.8)',
        paddingHorizontal: 8,
        paddingVertical: 3,
        borderRadius: 4,
    },
    consoleLoaderText: {
        fontSize: 8,
        color: '#00ffff',
        fontFamily: 'monospace',
        marginLeft: 6,
    },

    // PLAN
    planScroll: {
        flex: 1,
    },
    planContentContainer: {
        paddingBottom: 110,
    },
    planSectionHeader: {
        fontSize: 12,
        color: '#00ffff',
        fontWeight: 'bold',
        letterSpacing: 2,
        marginBottom: 10,
        borderBottomWidth: 1,
        borderBottomColor: 'rgba(0, 255, 255, 0.3)',
        paddingBottom: 4,
    },
    summaryText: {
        color: '#e2e8f0',
        fontSize: 12,
        lineHeight: 18,
        backgroundColor: 'rgba(0,0,0,0.3)',
        padding: 12,
        borderRadius: 8,
        borderLeftWidth: 3,
        borderLeftColor: '#00ffff',
        marginBottom: 14,
    },
    incidentCard: {
        borderWidth: 1,
        borderRadius: 8,
        backgroundColor: 'rgba(0,0,0,0.4)',
        borderLeftWidth: 4,
        marginBottom: 12,
        overflow: 'hidden',
    },
    incidentHeader: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: 12,
    },
    incidentHeaderLeft: {
        flexDirection: 'row',
        alignItems: 'center',
        flex: 1,
    },
    severityBadge: {
        borderWidth: 1,
        paddingHorizontal: 6,
        paddingVertical: 2,
        borderRadius: 4,
        marginRight: 8,
    },
    severityText: {
        fontWeight: 'bold',
        fontSize: 8,
        letterSpacing: 0.5,
    },
    incidentTitleText: {
        color: '#fff',
        fontWeight: 'bold',
        fontSize: 12,
        flex: 1,
    },
    incidentToggleIcon: {
        color: '#a0aec0',
        fontSize: 10,
        marginLeft: 8,
    },
    incidentDetails: {
        paddingHorizontal: 12,
        paddingBottom: 12,
        borderTopWidth: 1,
        borderTopColor: 'rgba(255,255,255,0.05)',
        paddingTop: 10,
        backgroundColor: 'rgba(0,0,0,0.2)',
    },
    detailLabel: {
        color: '#a0aec0',
        fontSize: 9,
        fontWeight: 'bold',
        letterSpacing: 1,
        marginTop: 8,
        marginBottom: 4,
    },
    detailContent: {
        color: '#e2e8f0',
        fontSize: 11,
        lineHeight: 16,
    },
    jiraSection: {
        borderTopWidth: 1,
        borderTopColor: 'rgba(255,255,255,0.05)',
        marginTop: 8,
    },
    discordSection: {
        borderTopWidth: 1,
        borderTopColor: 'rgba(255,255,255,0.05)',
        marginTop: 8,
    },
    codeSection: {
        borderTopWidth: 1,
        borderTopColor: 'rgba(255,255,255,0.05)',
        marginTop: 8,
    },
    codeScrollView: {
        backgroundColor: 'rgba(0,5,10,0.9)',
        borderRadius: 4,
        borderWidth: 1,
        borderColor: 'rgba(255,255,255,0.1)',
        padding: 8,
        marginTop: 4,
    },
    codeBlockText: {
        fontFamily: 'monospace',
        fontSize: 10,
        color: '#00ffaa',
    },

    // APPROVAL BAR
    approvalBar: {
        position: 'absolute',
        bottom: 0,
        left: 0,
        right: 0,
        backgroundColor: 'rgba(20, 25, 35, 0.95)',
        borderTopWidth: 1.5,
        borderTopColor: '#00ffff',
        padding: 14,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderTopLeftRadius: 12,
        borderTopRightRadius: 12,
        shadowColor: '#00ffff',
        shadowOffset: { width: 0, height: -4 },
        shadowOpacity: 0.15,
        shadowRadius: 10,
        elevation: 10,
    },
    approvalInfo: {
        flex: 1,
        marginRight: 10,
    },
    approvalStatusLabel: {
        fontSize: 8,
        color: '#a0aec0',
        fontWeight: 'bold',
        letterSpacing: 1,
    },
    approvalStatusTextPending: {
        fontSize: 10,
        color: '#ff8800',
        fontWeight: 'bold',
        letterSpacing: 0.5,
        marginTop: 2,
    },
    approvalStatusTextExecuting: {
        fontSize: 10,
        color: '#00ffff',
        fontWeight: 'bold',
        letterSpacing: 0.5,
        marginTop: 2,
    },
    approvalStatusTextSuccess: {
        fontSize: 10,
        color: '#10b981',
        fontWeight: 'bold',
        letterSpacing: 0.5,
        marginTop: 2,
    },
    approvalStatusTextFailed: {
        fontSize: 10,
        color: '#ef4444',
        fontWeight: 'bold',
        letterSpacing: 0.5,
        marginTop: 2,
    },
    approveButton: {
        backgroundColor: '#10b981',
        borderRadius: 6,
        paddingVertical: 10,
        paddingHorizontal: 16,
        justifyContent: 'center',
        alignItems: 'center',
    },
    approveButtonSuccess: {
        backgroundColor: 'rgba(16, 185, 129, 0.2)',
        borderWidth: 1,
        borderColor: '#10b981',
    },
    approveButtonDisabled: {
        opacity: 0.6,
    },
    approveButtonText: {
        color: '#fff',
        fontSize: 12,
        fontWeight: 'bold',
        letterSpacing: 1,
    },
});

export default AnalyzeScreen;