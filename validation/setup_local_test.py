#!/usr/bin/env python3
"""
Setup local test environment for DocuFlow validation
"""

import subprocess
import time
import os
import signal

def start_services():
    """Start all required services for local testing"""
    print("🚀 Starting DocuFlow test services...")
    
    # Start Python engine
    print("Starting Python engine...")
    engine_process = subprocess.Popen([
        "cd", "docuflow-engine", "&&", 
        ".", ".venv/bin/activate", "&&",
        "python", "-m", "uvicorn", "main:app", 
        "--host", "0.0.0.0", "--port", "8000"
    ], shell=True, preexec_fn=os.setsid)
    
    time.sleep(3)  # Wait for engine to start
    
    # Start API worker (simulated with wrangler dev)
    print("Starting API worker...")
    api_process = subprocess.Popen([
        "cd", "workers/api", "&&",
        "wrangler", "dev", "--port", "8787"
    ], shell=True, preexec_fn=os.setsid)
    
    time.sleep(5)  # Wait for workers to start
    
    # Start queue consumer
    print("Starting queue consumer...")
    consumer_process = subprocess.Popen([
        "cd", "workers/consumer", "&&",
        "wrangler", "dev", "--port", "8788"
    ], shell=True, preexec_fn=os.setsid)
    
    time.sleep(3)
    
    # Start events consumer
    print("Starting events consumer...")
    events_process = subprocess.Popen([
        "cd", "workers/events-consumer", "&&",
        "wrangler", "dev", "--port", "8789"
    ], shell=True, preexec_fn=os.setsid)
    
    print("✅ All services started!")
    print("API: http://localhost:8787")
    print("Engine: http://localhost:8000")
    
    return [engine_process, api_process, consumer_process, events_process]

def stop_services(processes):
    """Stop all services"""
    print("\n🛑 Stopping services...")
    for process in processes:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except:
            pass
    print("✅ Services stopped")

if __name__ == "__main__":
    processes = start_services()
    try:
        input("Press Enter to stop services...")
    except KeyboardInterrupt:
        pass
    finally:
        stop_services(processes)