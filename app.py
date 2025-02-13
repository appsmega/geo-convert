import streamlit as st
import pyproj
import ee
import re
import pandas as pd

st.set_page_config(page_title='Geo Convert')

# Função para autenticar e inicializar o Google Earth Engine
def inicializar_earth_engine():
    try:
        ee.Initialize(project='moonlit-outlet-450811-c7')
    except Exception as e:
        st.error(f"Erro ao inicializar o Google Earth Engine: {e}")
        st.info("Certifique-se de que você autenticou-se corretamente usando 'earthengine authenticate'.")
        return False
    return True

# Função para validar o formato das coordenadas
def validar_coordenadas(coord):
    # Expressão regular para validar o formato -xx.xxxxxxxx ou xx.xxxxxxxx
    padrao = r'^-?\d{1,2}\.\d{6,}$'
    return re.match(padrao, coord) is not None

# Função para verificar se as coordenadas estão no Brasil
def verificar_local_brasil(lat, lon):
    # Carrega um shapefile do Brasil (disponível no Google Earth Engine)
    brasil = ee.FeatureCollection("FAO/GAUL/2015/level0").filter(ee.Filter.eq('ADM0_NAME', 'Brazil'))
    
    # Cria um ponto com as coordenadas fornecidas
    ponto = ee.Geometry.Point([lon, lat])
    
    # Verifica se o ponto está dentro do Brasil usando spatial filter
    intersecao = brasil.filterBounds(ponto)
    
    # Se houver alguma interseção, o ponto está no Brasil
    return intersecao.size().getInfo() > 0

# Função para converter coordenadas geográficas para UTM
def convert_to_utm(lat, lon):
    # Calcula a zona UTM baseada na longitude
    zona_utm = int((lon + 180) / 6) + 1
    
    # Para o Brasil (hemisfério sul), usamos o código EPSG específico
    epsg_code = f"327{zona_utm:02d}"
    
    # Define os sistemas de coordenadas
    wgs84 = pyproj.CRS("EPSG:4326")  # WGS 84
    utm = pyproj.CRS(f"EPSG:{epsg_code}")  # UTM específico para a zona
    
    # Cria o transformador
    transformer = pyproj.Transformer.from_crs(wgs84, utm, always_xy=True)
    
    # Converte as coordenadas
    utm_x, utm_y = transformer.transform(lon, lat)
    return utm_x, utm_y

# Interface do usuário com Streamlit
st.markdown(
    '''
    <h2 style='text-align: center'>Coordenadas Geográficas para UTM</h2>
    ''', unsafe_allow_html=True
)

# Inicializa o Google Earth Engine
if not inicializar_earth_engine():
    st.stop()

# Criar duas abas: uma para entrada manual e outra para arquivo CSV
tab1, tab2 = st.tabs(["Conversão Única", "Conversão em Lote"])

with tab1:
    # Entrada manual de coordenadas
    lat = st.text_input("Insira a latitude (formato: -xx.xxxxxxxx):", value="-23.550520")
    lon = st.text_input("Insira a longitude (formato: -xx.xxxxxxxx):", value="-46.633308")

    if st.button("Converter Coordenadas"):
        if not validar_coordenadas(lat) or not validar_coordenadas(lon):
            st.error("Formato inválido! Use o formato -xx.xxxxxxxx ou xx.xxxxxxxx.")
        else:
            lat = float(lat)
            lon = float(lon)

            if not verificar_local_brasil(lat, lon):
                st.error("As coordenadas não correspondem a um local no Brasil.")
            else:
                utm_x, utm_y = convert_to_utm(lat, lon)
                st.success(f"Coordenadas UTM: X = {utm_x:.2f}, Y = {utm_y:.2f}")

with tab2:
    # Upload e processamento do arquivo CSV
    uploaded_file = st.file_uploader("Escolha o arquivo CSV", type='csv')
    st.markdown('''<p style="font-size: 10px">O arquivo deve conter colunas exatamente com os nomes Latitude e Longitude</p>''', unsafe_allow_html=True)
    
    if uploaded_file is not None:
        try:
            # Cria um placeholder para os logs
            log_placeholder = st.empty()
            
            # Lê o arquivo CSV
            log_placeholder.info("Iniciando leitura do arquivo CSV...")
            df = pd.read_csv(uploaded_file)
            
            # Adiciona o spinner para o processamento
            with st.spinner('Por favor aguarde...'):
                # Corrige os números dos postes
                log_placeholder.info("Preparando dados dos postes...")
                df['FreeText: N° do poste / PG'] = df['FreeText: N° do poste / PG'].apply(
                    lambda x: str(x).replace('\n', '').replace(' ', '') if pd.notna(x) else x
                )
                
                # Converte coordenadas para UTM
                utm_coords = []
                valid_coords = True
                total_rows = len(df)
                
                log_placeholder.info("Iniciando processamento das coordenadas...")
                
                # Processa cada linha
                for idx, row in df.iterrows():
                    # Atualiza o log a cada 10% do progresso
                    if idx % max(1, total_rows // 10) == 0:
                        progress = (idx / total_rows) * 100
                        log_placeholder.info(f"Processando coordenadas: {progress:.1f}% concluído...")
                    
                    lat, lon = row['Latitude'], row['Longitude']
                    
                    # Valida as coordenadas
                    if not (validar_coordenadas(str(lat)) and validar_coordenadas(str(lon))):
                        st.error(f"Formato inválido de coordenadas na linha {idx + 2}")
                        valid_coords = False
                        break
                    
                    # Verifica se está no Brasil
                    if not verificar_local_brasil(lat, lon):
                        st.error(f"Coordenadas da linha {idx + 2} não correspondem a um local no Brasil")
                        valid_coords = False
                        break
                    
                    # Converte para UTM
                    utm_x, utm_y = convert_to_utm(lat, lon)
                    utm_coords.append((utm_x, utm_y))
            
            if valid_coords:
                # Atualiza log
                log_placeholder.info("Finalizando processamento e preparando resultado...")
                
                # Adiciona as colunas UTM após Latitude e Longitude
                longitude_idx = df.columns.get_loc('Longitude')
                df.insert(longitude_idx + 1, 'X_UTM', [coord[0] for coord in utm_coords])
                df.insert(longitude_idx + 2, 'Y_UTM', [coord[1] for coord in utm_coords])
                
                # Limpa o placeholder de log e mostra o resultado
                log_placeholder.empty()
                
                # Mostra as primeiras linhas do resultado
                st.success('Processamento concluído com sucesso!')
                st.write("Primeiras linhas do arquivo processado:")
                st.write(df.head())
                
                # Botão para download do arquivo processado
                csv = df.to_csv(index=False)
                st.download_button(
                    label="Download do arquivo processado",
                    data=csv,
                    file_name="coordenadas_processadas.csv",
                    mime="text/csv"
                )
                
        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {str(e)}")