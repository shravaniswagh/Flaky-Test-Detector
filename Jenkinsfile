pipeline {
    agent any

    environment {
        PYTHON_VERSION = '3.11'
        PYTHONPATH      = "${WORKSPACE}/src/main"
        FLAKYSCAN_DB_PATH = "${WORKSPACE}/flakyscan.db"
    }

    options {
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
        disableConcurrentBuilds()
    }

    stages {

        stage('Setup') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install -r requirements.txt
                    pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    . venv/bin/activate
                    echo "=== flake8 ==="
                    flake8 src/main/ --max-line-length=120 --exclude=__pycache__
                    echo "=== pylint ==="
                    pylint src/main/*.py --disable=C0114,C0115,C0116 --fail-under=6.0 || true
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    python -m pytest src/test/sample_tests.py \
                        --junitxml=test-results/junit.xml \
                        -v --tb=short || true
                '''
            }
            post {
                always {
                    junit 'test-results/junit.xml'
                    archiveArtifacts artifacts: 'test-results/*.xml', allowEmptyArchive: true
                }
            }
        }

        stage('Flaky Detection') {
            steps {
                sh '''
                    . venv/bin/activate
                    python -c "
import json, sys
from flaky_detector import FlakyDetector
from test_analyzer import TestAnalyzer

detector = FlakyDetector(test_path='src/test/sample_tests.py', runs=3)
results = detector.run()
TestAnalyzer().batch_suggest(results)

flaky = [r for r in results if r['is_flaky']]
print(json.dumps({'flaky_count': len(flaky), 'total': len(results)}, indent=2))
for t in flaky:
    print(f'  FLAKY: {t[\"test_name\"]} ({t[\"failure_rate\"]*100:.0f}%)')
    if t.get('suggested_fix'):
        print(f'         Fix: {t[\"suggested_fix\"][:100]}')

with open('flaky-report.json', 'w') as f:
    json.dump(results, f, indent=2)
"
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'flaky-report.json', allowEmptyArchive: true
                }
            }
        }

        stage('Docker Build') {
            steps {
                sh "docker build -f infrastructure/docker/Dockerfile -t flakyscan:\${BUILD_NUMBER} ."
            }
        }

        stage('Docker Health Check') {
            steps {
                sh '''
                    docker run -d --name flakyscan-${BUILD_NUMBER} -p 8080:8080 \
                        -e FLAKYSCAN_DB_PATH=/app/data/flakyscan.db \
                        flakyscan:${BUILD_NUMBER}
                    sleep 5
                    curl -f http://localhost:8080/health
                '''
            }
            post {
                always {
                    sh """
                        docker stop flakyscan-\${BUILD_NUMBER} || true
                        docker rm flakyscan-\${BUILD_NUMBER} || true
                    """
                }
            }
        }
    }

    post {
        always {
            cleanWs()
        }
        success {
            echo 'Pipeline completed successfully.'
        }
        failure {
            echo 'Pipeline failed — check stage logs for details.'
        }
    }
}
