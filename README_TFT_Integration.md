# TFT-Enhanced Financial Forecasting System

A comprehensive **Temporal Fusion Transformer (TFT)** integration for your multi-agent financial analysis pipeline. This system enhances your existing `forecasting_analyst` with state-of-the-art machine learning capabilities while maintaining seamless CrewAI compatibility.

## Key Features

### Advanced ML Capabilities
- **Temporal Fusion Transformer**: State-of-the-art attention-based architecture
- **2+ Years Training Data**: Robust model training on extensive historical datasets
- **80+ Features**: Comprehensive technical indicators and market signals
- **5-Day Direction Classification**: Optimized for your existing pipeline

### Seamless Integration
- **Drop-in Replacement**: Works with your existing CrewAI agents
- **Fallback Mode**: Technical analysis when full ML training unavailable
- **Batch Predictions**: Efficient multi-ticker forecasting
- **Real-time Data**: yfinance integration for live market data

### Production Ready
- **Bias Control**: Prevents lookahead, overfitting, and data snooping
- **Error Handling**: Graceful degradation and comprehensive logging
- **Memory Efficient**: Optimized for practical deployment
- **Extensible**: Easy to add new features and models

## File Structure

```
├── tft_forecaster.py              # Core TFT implementation
├── crewai_tft_integration.py      # CrewAI tools and integration
├── enhanced_forecasting_analyst.py # Enhanced agent with TFT
├── requirements.txt               # Dependencies
├── README_TFT_Integration.md      # This file
└── models/                        # Saved models directory
```

## Installation

### 1. Install Dependencies

```bash
# Install core requirements
pip install -r requirements.txt

# Or install individually
pip install darts[torch] pytorch-forecasting ta yfinance pandas numpy
pip install crewai crewai-tools
```

### 2. Quick Setup Test

```python
# Test the basic system
from crewai_tft_integration import initialize_fallback_tft, tft_price_direction

# Initialize fallback system
result = initialize_fallback_tft()
print(result)

# Test prediction
prediction = tft_price_direction("AAPL")
print(prediction)
```

## Integration Options

### Option 1: Replace Existing Agent (Recommended)

```python
from enhanced_forecasting_analyst import create_enhanced_forecasting_analyst

# Replace your existing forecasting_analyst
forecasting_analyst = create_enhanced_forecasting_analyst(
    evaluation_start_date="2023-05-08",
    use_full_training=True  # or False for quick testing
)

# Use in your existing crew
analysis_crew = Crew(
    agents=[
        backtesting_agent,
        statistical_enricher_agent,
        forecasting_analyst,  # Enhanced version
        historical_trend_analyst,
        summary_agent
    ],
    tasks=[...],  # Your existing tasks
    process=Process.sequential
)
```

### Option 2: Enhance Existing Agent

```python
from enhanced_forecasting_analyst import enhance_existing_forecasting_agent

# Add TFT to your existing agent
enhanced_agent = enhance_existing_forecasting_agent(
    existing_agent=your_forecasting_analyst,
    evaluation_start_date="2023-05-08"
)
```

### Option 3: Direct Tool Integration

```python
from crewai_tft_integration import (
    train_tft_model, tft_price_direction, batch_tft_predictions
)

# Add tools to any existing agent
your_agent.tools.extend([
    train_tft_model,
    tft_price_direction,
    batch_tft_predictions
])
```

## Usage Examples

### Basic Prediction Workflow

```python
from crewai_tft_integration import *

# 1. Initialize system (choose one)
train_tft_model("2023-05-08")  # Full training
# OR
initialize_fallback_tft()      # Quick technical analysis

# 2. Check status
status = tft_model_status()
print(status)

# 3. Make predictions
prediction = tft_price_direction("AAPL")
print(prediction)  # Output: "AAPL: Buy (conf=0.73, prob_up=0.78, model=tft)"

# 4. Batch predictions
batch_result = batch_tft_predictions("AAPL,MSFT,GOOGL")
print(batch_result)
```

### Data Quality Validation

```python
# Preview training data quality
sample = get_training_data_sample("2023-05-08", "AAPL,MSFT")
print(sample)

# Output:
# Training Data Sample Summary:
# - Date range: 2021-04-07 to 2023-05-07
# - Total samples: 1,567
# - Tickers: AAPL, MSFT
# - Features: 87
# - Target balance: 52.3% up, 47.7% down
# - Missing data: 0.12%
# Data quality looks good for TFT training
```

### Complete Analysis Crew

```python
from enhanced_forecasting_analyst import create_tft_analysis_crew

# Create complete crew with TFT forecasting
tft_crew = create_tft_analysis_crew(
    evaluation_start_date="2023-05-08",
    training_tickers="AAPL,MSFT,GOOGL,NVDA,TSLA",
    use_full_training=True
)

# Run the analysis
results = tft_crew.kickoff()
```

## Model Architecture

### TFT Implementation Details

**Input Features (80+)**:
- **Price Signals**: OHLCV, returns, ratios
- **Technical Indicators**: RSI, MACD, Bollinger Bands, Stochastic, Williams %R
- **Moving Averages**: SMA/EMA (5,10,20,50,200) + crossovers
- **Momentum**: Multiple timeframes (1,3,5,10,20 days)
- **Volatility**: Rolling standard deviations, ATR
- **Volume**: Analysis, trends, momentum
- **Market Features**: SPY correlation, VIX proxy, sector signals
- **Time Features**: Day of week, month, quarter, earnings calendars

**Model Parameters**:
```python
{
    'input_chunk_length': 60,     # 60-day lookback window
    'output_chunk_length': 5,     # 5-day prediction horizon
    'hidden_size': 128,           # Model capacity
    'lstm_layers': 2,             # Sequence modeling depth
    'num_attention_heads': 8,     # Multi-head attention
    'dropout': 0.2,               # Regularization
    'batch_size': 128,            # Training efficiency
    'n_epochs': 50                # Training duration
}
```

### Training Strategy

**Global Model Approach**:
- Single model trained across multiple tickers
- Learns cross-stock patterns and market regimes
- More robust than individual ticker models
- Better generalization to new stocks

**Data Preparation**:
- **Training Period**: 2+ years before evaluation
- **Target**: 5-day binary direction classification
- **Features**: Technical + market + sentiment indicators
- **Validation**: 80/20 train/validation split

## Performance & Validation

### Bias Control Measures

1. **Lookahead Prevention**: No future data in feature engineering
2. **Data Snooping**: Train only on pre-evaluation period
3. **Overfitting**: Regularization + validation splits
4. **Confirmation Bias**: Report conflicting signals
5. **Survivorship Bias**: Include delisted stocks in training

### Fallback Mechanisms

**When TFT Unavailable**:
- Technical analysis-based predictions
- Multi-signal momentum analysis
- Volatility-adjusted confidence scores
- Graceful degradation maintains functionality

**Error Handling**:
- Data collection failures → neutral predictions
- Model training errors → fallback mode
- Prediction errors → technical analysis backup

## Customization

### Adding New Features

```python
def custom_feature_engineering(df):
    # Add your custom indicators
    df['custom_indicator'] = your_calculation(df)
    return df

# Extend the FinancialDataProcessor
processor = FinancialDataProcessor()
processor._engineer_features = custom_feature_engineering
```

### Model Hyperparameters

```python
custom_params = {
    'input_chunk_length': 90,  # Longer lookback
    'hidden_size': 256,        # Larger model
    'n_epochs': 100           # More training
}

forecaster = TFTForecaster(model_params=custom_params)
```

### Custom Training Data

```python
# Use specific tickers and date ranges
training_data = create_training_data(
    evaluation_start_date="2023-05-08",
    tickers=["AAPL", "MSFT", "GOOGL"]  # Custom ticker list
)
```

## Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Install missing dependencies
pip install darts[torch] pytorch-forecasting ta
```

**2. Training Failures**
```python
# Use fallback mode for testing
initialize_fallback_tft()
```

**3. Memory Issues**
```python
# Reduce batch size or model size
custom_params = {'batch_size': 64, 'hidden_size': 64}
```

**4. Data Quality Issues**
```python
# Validate data first
sample = get_training_data_sample("2023-05-08", "AAPL")
print(sample)
```

### Debugging Tips

```python
# Check model status
status = tft_model_status()
print(status)

# Test individual components
from tft_forecaster import FinancialDataProcessor
processor = FinancialDataProcessor()
data = processor.collect_historical_data(["AAPL"], "2022-01-01", "2023-01-01")
print(f"Collected {len(data)} samples")
```

## Integration with Your Existing System

### Your Current Forecasting Task

Replace this in your notebook:
```python
forecasting_analyst = Agent(
    role='Short-Term Forecasting Analyst',
    goal='Predict 5-day direction...',
    backstory='...',
    verbose=True
)
```

With this:
```python
from enhanced_forecasting_analyst import create_enhanced_forecasting_analyst

forecasting_analyst = create_enhanced_forecasting_analyst(
    evaluation_start_date="2023-05-08",  # Your evaluation period
    use_full_training=True
)
```

### Task Updates

Your existing `forecasting_task` can remain mostly the same, but consider enhancing it:

```python
forecasting_task = Task(
    description=(
        "Use the TFT prediction system to forecast 5-day price directions. "
        "Start by calling tft_model_status() to check initialization. "
        "Use batch_tft_predictions() for efficient multi-ticker analysis. "
        # ... rest of your existing task description
    ),
    expected_output="...",  # Your existing output format
    agent=forecasting_analyst
)
```

## Next Steps

### Phase 1: TFT (Complete)
- Temporal Fusion Transformer implementation
- Comprehensive feature engineering
- CrewAI integration tools
- Production-ready deployment

### Phase 2: PatchTST (Future)
- Vision-style patch embedding
- State-of-the-art M4/M5 performance
- Ensemble with TFT

### Phase 3: Informer/Autoformer (Future)
- Memory-efficient long horizons
- Advanced attention mechanisms
- Multi-model voting system

## Support

For questions or issues:
1. Check the troubleshooting section above
2. Validate data quality with `get_training_data_sample()`
3. Test with fallback mode: `initialize_fallback_tft()`
4. Review logs for detailed error messages

## Summary

This TFT integration provides:
- **State-of-the-art ML**: Advanced transformer architecture
- **Seamless Integration**: Drop-in replacement for existing agents
- **Production Ready**: Comprehensive error handling and fallbacks
- **Extensible**: Easy to customize and extend

Ready to enhance your financial forecasting with cutting-edge ML! 