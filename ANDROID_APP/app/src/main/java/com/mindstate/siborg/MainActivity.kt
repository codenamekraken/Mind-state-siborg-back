package com.mindstate.siborg

import android.Manifest
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothGattService
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanFilter
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.graphics.Bitmap
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.mindstate.siborg.databinding.ActivityMainBinding
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    private val serviceUuid: UUID = UUID.fromString("6e400001-b5a3-f393-e0a9-e50e24dcca9e")
    private val charUuid: UUID = UUID.fromString("6e400003-b5a3-f393-e0a9-e50e24dcca9e")
    private val cccdUuid: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    private val handler = Handler(Looper.getMainLooper())
    private var bluetoothGatt: BluetoothGatt? = null
    private var scanner: BluetoothLeScanner? = null
    private var isScanning = false
    private var currentQuestionIndex = 0
    private val questions = listOf(
        "I found it hard to wind down.",
        "I felt close to panic.",
        "I found it difficult to relax.",
        "I felt down-hearted and blue.",
        "I felt I was using a lot of nervous energy."
    )

    private val checkInUrl: String get() = BuildConfig.CHECKIN_URL
    private val backendUrl: String get() = BuildConfig.BACKEND_URL

    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { result ->
        val granted = result.values.all { it }
        if (granted) startBleScan() else toast("Bluetooth permissions denied")
    }

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) takePicturePreviewLauncher.launch(null)
        else toast("Camera permission denied")
    }

    private val takePicturePreviewLauncher = registerForActivityResult(
        ActivityResultContracts.TakePicturePreview()
    ) { bitmap: Bitmap? ->
        if (bitmap != null) {
            binding.imgFacePreview.setImageBitmap(bitmap)
            binding.txtFaceStatus.text = "Face captured successfully"
            binding.txtFaceStatus.setTextColor(Color.parseColor("#34D399"))
            showQuestionSection()
        } else {
            toast("Face capture cancelled")
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.txtBackendUrl.text = backendUrl
        binding.txtFrontendUrl.text = checkInUrl

        binding.btnConnectSensor.setOnClickListener { ensureBlePermissionsThenScan() }
        binding.btnDisconnectSensor.setOnClickListener { disconnectSensor() }
        binding.btnOpenWeb.setOnClickListener { openWebFallback() }
        binding.btnCamera.setOnClickListener { startFaceCaptureStep() }
        binding.btnVoice.setOnClickListener {
            binding.txtVoiceStatus.text = "Voice step active (native recorder can be added next)"
            binding.txtVoiceStatus.setTextColor(Color.parseColor("#FDE68A"))
            toast("Voice step enabled")
        }
        binding.btnDass.setOnClickListener { showQuestionSection() }
        binding.btnNextQuestion.setOnClickListener { moveToNextQuestion() }

        setSensorStatus("Not connected", false)
        binding.faceSection.visibility = View.GONE
        binding.questionSection.visibility = View.GONE
        updateQuestionUi()
        refreshBackendHealth()
    }

    override fun onDestroy() {
        super.onDestroy()
        stopBleScan()
        bluetoothGatt?.close()
        bluetoothGatt = null
    }

    private fun refreshBackendHealth() {
        binding.txtBackendHealth.text = "Checking backend..."
        thread {
            val msg = try {
                val url = URL("$backendUrl/health")
                val conn = (url.openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    connectTimeout = 5000
                    readTimeout = 5000
                }
                val text = conn.inputStream.bufferedReader().use { it.readText() }
                if (text.contains("\"status\":\"ok\"")) "Backend: Online" else "Backend: Degraded"
            } catch (_: Exception) {
                "Backend: Offline"
            }
            runOnUiThread { binding.txtBackendHealth.text = msg }
        }
    }

    private fun ensureBlePermissionsThenScan() {
        val required = mutableListOf<String>()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (!hasPermission(Manifest.permission.BLUETOOTH_SCAN)) required.add(Manifest.permission.BLUETOOTH_SCAN)
            if (!hasPermission(Manifest.permission.BLUETOOTH_CONNECT)) required.add(Manifest.permission.BLUETOOTH_CONNECT)
        } else {
            if (!hasPermission(Manifest.permission.ACCESS_FINE_LOCATION)) required.add(Manifest.permission.ACCESS_FINE_LOCATION)
        }

        if (required.isNotEmpty()) {
            permissionLauncher.launch(required.toTypedArray())
        } else {
            startBleScan()
        }
    }

    private fun startBleScan() {
        if (isScanning) return

        val manager = getSystemService(BLUETOOTH_SERVICE) as BluetoothManager
        val adapter = manager.adapter
        if (adapter == null || !adapter.isEnabled) {
            toast("Enable Bluetooth first")
            return
        }

        scanner = adapter.bluetoothLeScanner
        if (scanner == null) {
            toast("BLE scanner not available")
            return
        }

        val filters = listOf(
            ScanFilter.Builder().setDeviceName("Mind-state-siborg_Device").build(),
            ScanFilter.Builder().setServiceUuid(android.os.ParcelUuid(serviceUuid)).build()
        )
        val settings = ScanSettings.Builder()
            .setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY)
            .build()

        setSensorStatus("Scanning for sensor...", false)
        scanner?.startScan(filters, settings, scanCallback)
        isScanning = true

        handler.postDelayed({
            if (isScanning) {
                stopBleScan()
                setSensorStatus("Sensor not found. Keep ESP32 close and retry.", false)
            }
        }, 12000)
    }

    private fun stopBleScan() {
        if (!isScanning) return
        try {
            scanner?.stopScan(scanCallback)
        } catch (_: Exception) {
        }
        isScanning = false
    }

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            super.onScanResult(callbackType, result)
            val device = result.device ?: return
            val name = device.name ?: "Unknown"
            if (name.contains("Mind-state-siborg", ignoreCase = true) || hasService(result)) {
                stopBleScan()
                connectGatt(device)
            }
        }
    }

    private fun hasService(result: ScanResult): Boolean {
        val uuids = result.scanRecord?.serviceUuids ?: return false
        return uuids.any { it.uuid == serviceUuid }
    }

    private fun connectGatt(device: BluetoothDevice) {
        setSensorStatus("Connecting to ${device.name ?: "sensor"}...", false)
        bluetoothGatt?.close()
        bluetoothGatt = device.connectGatt(this, false, gattCallback)
    }

    private val gattCallback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(gatt: BluetoothGatt, status: Int, newState: Int) {
            super.onConnectionStateChange(gatt, status, newState)
            runOnUiThread {
                when (newState) {
                    BluetoothGatt.STATE_CONNECTED -> {
                        setSensorStatus("Connected. Discovering services...", true)
                        gatt.discoverServices()
                    }
                    BluetoothGatt.STATE_DISCONNECTED -> {
                        setSensorStatus("Disconnected", false)
                    }
                    else -> Unit
                }
            }
        }

        override fun onServicesDiscovered(gatt: BluetoothGatt, status: Int) {
            super.onServicesDiscovered(gatt, status)
            val service: BluetoothGattService? = gatt.getService(serviceUuid)
            val characteristic: BluetoothGattCharacteristic? = service?.getCharacteristic(charUuid)
            if (characteristic == null) {
                runOnUiThread { setSensorStatus("Sensor characteristic missing", false) }
                return
            }

            val notifyOk = gatt.setCharacteristicNotification(characteristic, true)
            val descriptor = characteristic.getDescriptor(cccdUuid)
            if (descriptor != null) {
                descriptor.value = BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE
                gatt.writeDescriptor(descriptor)
            }
            runOnUiThread {
                if (notifyOk) setSensorStatus("Live sensor stream started", true)
                else setSensorStatus("Connected but notify failed", false)
            }
        }

        @Suppress("DEPRECATION")
        override fun onCharacteristicChanged(gatt: BluetoothGatt, characteristic: BluetoothGattCharacteristic) {
            super.onCharacteristicChanged(gatt, characteristic)
            val payload = characteristic.value?.decodeToString().orEmpty()
            if (payload.isBlank()) return
            runOnUiThread { renderSensorPayload(payload) }
        }
    }

    private fun renderSensorPayload(payload: String) {
        try {
            val obj = JSONObject(payload)
            val bpm = obj.optInt("bpm", 0)
            val spo2 = obj.optInt("spo2", 0)
            val hrv = obj.optDouble("hrv_rmssd", 0.0)
            val temp = obj.optDouble("temp_c", 0.0)

            binding.txtBpmValue.text = if (bpm > 0) "$bpm bpm" else "--"
            binding.txtSpo2Value.text = if (spo2 > 0) "$spo2 %" else "--"
            binding.txtHrvValue.text = if (hrv > 0.0) String.format("%.1f ms", hrv) else "--"
            binding.txtTempValue.text = if (temp > 0.0) String.format("%.1f °C", temp) else "--"
            binding.txtFaceVitals.text = "Live during face • BPM: " +
                (if (bpm > 0) "$bpm" else "--") +
                "  SpO₂: " + (if (spo2 > 0) "$spo2%" else "--")
            binding.txtQuestionVitals.text = "Live during questions • BPM: " +
                (if (bpm > 0) "$bpm" else "--") +
                "  SpO₂: " + (if (spo2 > 0) "$spo2%" else "--")
            binding.txtRawPayload.text = payload
        } catch (_: Exception) {
            binding.txtRawPayload.text = payload
        }
    }

    private fun startFaceCaptureStep() {
        if (!deviceConnected) {
            toast("Connect sensor first for live heartbeat")
            return
        }
        if (!hasPermission(Manifest.permission.CAMERA)) {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
            return
        }
        binding.faceSection.visibility = View.VISIBLE
        binding.questionSection.visibility = View.GONE
        binding.txtFaceStatus.text = "Opening camera..."
        binding.txtFaceStatus.setTextColor(Color.parseColor("#FDE68A"))
        takePicturePreviewLauncher.launch(null)
    }

    private fun showQuestionSection() {
        if (!deviceConnected) {
            toast("Connect sensor first for live BPM during questions")
            return
        }
        binding.faceSection.visibility = View.VISIBLE
        binding.questionSection.visibility = View.VISIBLE
        currentQuestionIndex = 0
        binding.btnNextQuestion.isEnabled = true
        binding.btnNextQuestion.alpha = 1.0f
        binding.txtQuestionVitals.text = "Live during questions • waiting sensor values..."
        updateQuestionUi()
    }

    private fun updateQuestionUi() {
        val index = currentQuestionIndex.coerceIn(0, questions.lastIndex)
        binding.txtQuestionCounter.text = "Question ${index + 1} / ${questions.size}"
        binding.txtQuestionText.text = questions[index]
        binding.btnNextQuestion.text = if (index == questions.lastIndex) "Finish Questions" else "Next Question"
    }

    private fun moveToNextQuestion() {
        if (currentQuestionIndex < questions.lastIndex) {
            currentQuestionIndex += 1
            updateQuestionUi()
            return
        }
        binding.txtQuestionCounter.text = "Questions completed"
        binding.txtQuestionText.text = "Great job. Live BPM/SpO₂ stayed active throughout this stage."
        binding.btnNextQuestion.isEnabled = false
        binding.btnNextQuestion.alpha = 0.6f
    }

    private fun disconnectSensor() {
        stopBleScan()
        bluetoothGatt?.disconnect()
        bluetoothGatt?.close()
        bluetoothGatt = null
        setSensorStatus("Disconnected", false)
    }

    private fun setSensorStatus(text: String, connected: Boolean) {
        binding.txtSensorStatus.text = text
        binding.txtSensorStatus.setTextColor(if (connected) Color.parseColor("#34D399") else Color.parseColor("#F87171"))
    }

    private fun hasPermission(permission: String): Boolean {
        return ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED
    }

    private fun openWebFallback() {
        startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(checkInUrl)))
    }

    private fun toast(msg: String) {
        Toast.makeText(this, msg, Toast.LENGTH_SHORT).show()
    }
}
